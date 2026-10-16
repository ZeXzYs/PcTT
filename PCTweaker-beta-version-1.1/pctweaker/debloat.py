"""Built-in app removal (curated list only)."""
import re

from .admin import powershell

# (package name, label, ticked by default)
APPS = [
    ("Clipchamp.Clipchamp", "Clipchamp video editor", True),
    ("Microsoft.BingNews", "Microsoft News", True),
    ("Microsoft.BingWeather", "Weather", True),
    ("Microsoft.BingSearch", "Bing Search", True),
    ("Microsoft.GetHelp", "Get Help", True),
    ("Microsoft.Getstarted", "Tips", True),
    ("Microsoft.MicrosoftOfficeHub", "Microsoft 365 hub", True),
    ("Microsoft.MicrosoftSolitaireCollection", "Solitaire Collection", True),
    ("Microsoft.People", "People", True),
    ("Microsoft.PowerAutomateDesktop", "Power Automate", True),
    ("Microsoft.Todos", "Microsoft To Do", True),
    ("Microsoft.WindowsFeedbackHub", "Feedback Hub", True),
    ("Microsoft.WindowsMaps", "Maps", True),
    ("Microsoft.MixedReality.Portal", "Mixed Reality Portal", True),
    ("Microsoft.3DBuilder", "3D Builder", True),
    ("Microsoft.Microsoft3DViewer", "3D Viewer", True),
    ("Microsoft.Print3D", "Print 3D", True),
    ("Microsoft.SkypeApp", "Skype", True),
    ("MicrosoftTeams", "Microsoft Teams (personal)", True),
    ("Microsoft.549981C3F5F10", "Cortana", True),
    ("Microsoft.YourPhone", "Phone Link", False),
    ("Microsoft.ZuneMusic", "Media Player / Groove Music", False),
    ("Microsoft.ZuneVideo", "Movies & TV", False),
    ("Microsoft.OutlookForWindows", "Outlook (new)", False),
    ("Microsoft.MicrosoftStickyNotes", "Sticky Notes", False),
    ("Microsoft.Windows.DevHome", "Dev Home", False),
    ("Microsoft.GamingApp", "Xbox app", False),
    ("Microsoft.XboxGamingOverlay", "Xbox Game Bar", False),
]

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def remove_apps(package_names):
    """Remove the given packages. Returns {'removed': [...], 'kept': [...], 'absent': [...]}."""
    known = {a[0] for a in APPS}
    names = [n for n in package_names if n in known and _SAFE.match(n)]
    if not names:
        return {"removed": [], "kept": [], "absent": []}
    arr = ",".join(f"'{n}'" for n in names)
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        f"foreach($n in @({arr})){{"
        "$had=[bool](Get-AppxPackage -AllUsers -Name $n);"
        "if($had){Get-AppxPackage -AllUsers -Name $n | Remove-AppxPackage -AllUsers};"
        "Get-AppxProvisionedPackage -Online | Where-Object {$_.DisplayName -eq $n} | "
        "Remove-AppxProvisionedPackage -Online | Out-Null;"
        "if(-not $had){Write-Output \"ABSENT:$n\"}"
        "elseif(Get-AppxPackage -AllUsers -Name $n){Write-Output \"KEPT:$n\"}"
        "else{Write-Output \"REMOVED:$n\"}}"
    )
    rc, out = powershell(script, timeout=900)
    res = {"removed": [], "kept": [], "absent": []}
    for line in out.splitlines():
        tag, _, name = line.strip().partition(":")
        key = {"REMOVED": "removed", "KEPT": "kept", "ABSENT": "absent"}.get(tag)
        if key:
            res[key].append(name)
    if not any(res.values()):
        raise RuntimeError(out.strip() or "PowerShell returned no result.")
    return res
