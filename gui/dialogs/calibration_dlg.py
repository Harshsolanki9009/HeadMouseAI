"""Interactive Camera Calibration Dialog for HeadMouseAI.

Exposes CalibrationWizard as the primary 6-step calibration dialog while preserving
backward compatibility with CalibrationDialog.
"""

from __future__ import annotations

from gui.dialogs.calibration_wizard import CalibrationWizard

# Primary 6-step interactive wizard
CalibrationDialog = CalibrationWizard

__all__ = ["CalibrationWizard", "CalibrationDialog"]
