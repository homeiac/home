"""Stable cricket extensions to the shared OpenLABEL vocabulary; never recycle codes."""

VERSION = "cricket-1"
COMPLETION_VERSION = "cricket-2"
COMPLETION = "CRK.CTX.001"
# cricket-2 adds a source-analysis completion context; all cricket-1 codes remain.
# Definitions describe saved assertions, whose review state remains explicit.
ACTIONS = {
    "batting": ("CRK.ACT.001", "Playing as the batter in the observed delivery."),
    "bowling": ("CRK.ACT.002", "Delivering the ball as the bowler."),
    "other": ("CRK.ACT.003", "An observed cricket role outside batting or bowling."),
    "unknown": ("CRK.ACT.004", "The cricket role has not been established."),
}
OUTCOMES = {
    "four": ("CRK.OUT.001", "A four-run boundary is suggested or confirmed."),
    "six": ("CRK.OUT.002", "A six-run boundary is suggested or confirmed."),
    "boundary_unclear": (
        "CRK.OUT.003",
        "A boundary is supported but four versus six is unresolved.",
    ),
    "dismissal": (
        "CRK.OUT.004",
        "A batter is out; dismissal method or bowler credit is separate.",
    ),
    "run_out": ("CRK.OUT.005", "A completed run-out; not credited to the bowler."),
    "attempted_run_out": (
        "CRK.OUT.006",
        "An attempted run-out with the batter not out.",
    ),
    "other": ("CRK.OUT.007", "A known outcome outside the listed highlight results."),
    "unknown": ("CRK.OUT.008", "The delivery outcome has not been established."),
}
