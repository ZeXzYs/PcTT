"""PC Tweaker entry point."""
import os
import sys
import traceback


def _crash(text: str):
    try:
        from pctweaker.config import data_dir
        (data_dir() / "crash.log").write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("PC Tweaker crashed", text[-1500:] + "\n\n(A copy was saved to %APPDATA%\\PCTweaker\\crash.log)")
    except Exception:
        pass


def main():
    if sys.platform != "win32":
        print("PC Tweaker only runs on Windows.")
        sys.exit(1)
    os.chdir(os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)))
    try:
        from pctweaker.app import App
        App().mainloop()
    except Exception:
        _crash(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
