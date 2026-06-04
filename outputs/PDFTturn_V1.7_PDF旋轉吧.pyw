from pathlib import Path
import runpy


runpy.run_path(
    str(Path(__file__).with_name("PDFTturn_V1.7_PDF旋轉吧.py")),
    run_name="__main__",
)
