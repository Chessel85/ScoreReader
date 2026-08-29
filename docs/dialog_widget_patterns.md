# Dialog list/button patterns

Developer reference (not end-user facing - see `docs/user_guide.md` for that).
Distilled from getting `widgets/attribute_order_dialog.py` and
`widgets/part_order_dialog.py` right through live NVDA testing
(2026-08-29). Follow this for any new dialog that pairs a reorderable
`QListWidget` with Move Up/Move Down buttons, or more generally any dialog
mixing plain `QPushButton`s with a `QDialogButtonBox`.

## The autoDefault trap (read this first)

A `QPushButton`'s `autoDefault` property (`True` by default for every plain
`QPushButton`) is not just "is this the dialog's default button." Qt
dynamically **hands default status to whichever autoDefault button
currently has keyboard focus** - that's the literal meaning of "auto":
Tab onto any autoDefault button and it silently becomes the dialog's
effective default for as long as it holds focus, taking that status away
from whatever button (e.g. Ok) held it before.

This matters for accessibility specifically: a screen reader's announced
"keyboard shortcut" for a button is generated from that same live
default-button flag, not from its mnemonic alone. The practical effect:
**a `QPushButton` with a `&`-mnemonic (e.g. `"Move &Up"`) and `autoDefault`
left at its default `True` will have NVDA announce "Enter" instead of
"Alt+U"** the moment the user tabs to it - silently masking the real
mnemonic.

**This is only observable with a real, activated window.** The offscreen
Qt platform this project's whole test suite runs under
(`QT_QPA_PLATFORM=offscreen`, see `tests/conftest.py`) never gives a widget
real OS focus or a real window-activation event, so `button.isDefault()`
and `QAccessible.queryAccessibleInterface(button).text(QAccessible.Text.Accelerator)`
both report the "obviously correct" static values even when live NVDA
testing shows the opposite. **Don't trust an offscreen accessibility check
to settle a question about default-button/mnemonic interaction - it isn't
reliable for this, only live testing (or documented Qt behaviour) is.**

### The fix, and its trade-off

For every button in the dialog that is NOT the thing Enter should activate
(i.e. every button except `Ok`/whichever button is genuinely the default):

```python
self.up_button = QPushButton("Move &Up", self)
self.up_button.setAutoDefault(False)
```

And make the real default explicit rather than relying on
`QDialogButtonBox`'s own implicit default-button assignment (also
timing-dependent on a real window - it can be won by an earlier-created
plain `QPushButton` instead of `Ok` if you don't do this):

```python
buttons = QDialogButtonBox(
    QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
)
buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
```

**Trade-off, confirmed with the user as the deliberate choice for this
project**: with `autoDefault=False`, a focused non-default button no
longer responds to Enter itself - Enter instead bubbles up and triggers
the dialog's real default (Ok). Space is unaffected either way (a focused
`QAbstractButton` always handles Space directly, regardless of
`autoDefault`) - so Space still activates Up/Down/etc. Getting Enter to
ALSO activate a non-default button itself, without it stealing default
status and masking its own mnemonic, is not achievable through plain Qt
properties - it would need a small bespoke key handler consuming that
button's own Enter, which this project has chosen not to add. If a future
dialog genuinely needs that (Enter-on-a-non-default-button performs its
action), that inherent conflict needs re-raising with the user, not
silently resolved either way.

## Working-copy Ok/Cancel dialogs (staged edits, not live-apply)

For a dialog that lets the user reorder/edit something and should only
commit on Ok (discarding on Cancel/Escape/close-box), follow
`widgets/part_order_dialog.py` (or `widgets/attribute_order_dialog.py`,
which was migrated to this exact shape from an earlier live-apply design -
see its own docstring and CLAUDE.md's Architecture section for why):

- The dialog owns a **local, in-memory `QListWidget`** built from the
  data passed into `__init__`. Move Up/Down (`_move(delta)`) reorder that
  local list ONLY - `takeItem`/`insertItem`, nothing else - and never touch
  the model (`MusicData` or whatever owns the real data).
- Expose the final order via a plain getter (`ordered_keys()`/
  `part_order()`), read by the caller only after `exec()` returns
  `QDialog.DialogCode.Accepted`.
- The dialog class itself never imports or touches the model layer - it
  is a pure view, same as every other dialog in `widgets/`. The caller
  (a `main_window.py` `_show_*_dialog` method, delegating to the
  relevant controller in `controllers/`) does the actual commit.
- **Never call `setFocus()` on the list (or anything else) after a
  button-driven move.** A caller pressing Space repeatedly on Up/Down to
  walk an item up several rows needs focus to STAY on the button between
  presses - forcibly refocusing the list after every move breaks that
  (reported live: "this prevents me pressing the up button with spacebar
  multiple times in succession"). Only set focus once, in `showEvent`
  (deferred via `QTimer.singleShot(0, ...)`, same reasoning as
  `widgets/goto_measure_dialog.py` - `setFocus()` before the native window
  exists never reaches NVDA).

## Initial focus must also re-announce the current row (NVDA+Up gotcha)

Reported live (2026-08-29): opening a dialog like Reorder Attributes and
immediately asking NVDA to read the current line (NVDA+Up) read whatever had
focus *before* the dialog opened, not the dialog's own list - only moving
Up/Down (or Tab) once inside the dialog made NVDA start reading it
correctly.

Root cause: every list-based dialog here sets its list's initial current row
in `__init__`/`_populate`, before the dialog's native window exists. At that
point `QAbstractItemView::hasFocus()` is still `False`, and Qt's own
accessibility plumbing (`qabstractitemview.cpp`'s `currentChanged` handler)
only posts a `QAccessible::Focus` event for the **item** when the view
already has focus at the moment `currentChanged` fires. A bare
`list_widget.setFocus()` in `showEvent` (the idiom described above) only
posts a widget-level Focus event - nothing ever tells NVDA which row is
current. A manual Up/Down press fixes it because that keypress is the
first `currentChanged` to fire while the view genuinely has focus.

**Fix**: use `focus_list_and_reannounce_current_row` from
`widgets/list_focus_helper.py` in `showEvent` instead of a bare
`list_widget.setFocus()`, still deferred via `QTimer.singleShot(0, ...)`:

```python
from widgets.list_focus_helper import focus_list_and_reannounce_current_row

def showEvent(self, event):
    super().showEvent(event)
    QTimer.singleShot(0, lambda: focus_list_and_reannounce_current_row(self.attribute_list))
```

It calls `setFocus()` then toggles the current row to `-1` and back, which
forces a real `currentRowChanged` transition now that the view has focus -
reproducing what a manual Up/Down keypress already does, without changing
which row ends up selected. **The three steps must be spaced across real
timer delays (`_STEP_DELAY_MS`, 120 ms each), not fired in one synchronous
burst** - a first attempt that did all three in a single
`QTimer.singleShot(0, ...)` callback did NOT fix the bug live (NVDA still
spoke the previous window's stale text, both on the dialog's automatic
open-announcement and on a follow-up NVDA+Up); spacing them out did.
Confirmed live with NVDA (2026-08-29): NVDA+Up now reads the dialog's
actual current row on the first try. **Accepted trade-off**: the dialog's
opening announcement is now spoken twice (once for the real focus-in, once
more when the delayed toggle replays it) - confirmed with the user as
worth it for NVDA+Up actually working correctly.

Applied to every dialog whose list has an initial current row set before
it's shown: `AttributeOrderDialog`, `PartOrderDialog`, `FindDialog`,
`MixerDialog`, `InstrumentDialog`, `PerformanceReportDialog`. A dialog
whose initial focus target is a `QComboBox`/`QLineEdit`/`QCheckBox` instead
of a list doesn't need this - there's no separate "current item" child
object distinct from the widget itself for those controls, so a bare
`setFocus()` already reports the right value.

## Restoring focus after the dialog closes

Every `_show_*_dialog` method in `main_window.py` wraps its dialog
construction/`exec()` in `with self._preserving_focus():` (see that
context manager's own docstring, `main_window.py`). This restores focus to
whatever held it *before* the dialog opened, regardless of Ok/Cancel/
Escape/close-box. **Never hardcode a `some_widget.setFocus()` call after
`exec()` returns** on the assumption of "where the dialog's context came
from" - that breaks the moment the dialog can be invoked from more than
one place, and it was reported live as wrong behaviour
(`_show_attribute_order_dialog` used to force focus to Region 2
unconditionally; fixed by switching to `_preserving_focus()` like every
other dialog).

## Quick checklist for a new list+buttons dialog

1. `QListWidgetItem` + `Qt.ItemDataRole.UserRole` to carry the real key/id
   alongside the display label (see `_populate` in either reference
   dialog).
2. Move Up/Down as local-only `_move(delta)`, no signals to the caller.
3. `setAutoDefault(False)` on every button except the real default.
4. `buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)`
   explicitly.
5. `showEvent` defers initial focus via `QTimer.singleShot(0, ...)`, using
   `focus_list_and_reannounce_current_row` (see above) rather than a bare
   `setFocus()` when the initial focus target is a list with a pre-set
   current row; nothing else in the dialog calls `setFocus()`.
6. Caller wraps construction+`exec()` in `self._preserving_focus()` and
   only commits on `QDialog.DialogCode.Accepted`.
