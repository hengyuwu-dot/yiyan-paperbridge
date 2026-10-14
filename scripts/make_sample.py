"""A synthetic SCI-style fixture. No real scientific results are asserted."""
from pathlib import Path
import sys

import pymupdf as fitz

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "examples" / "sci-layout-sample.pdf"


def write(page, rect, text, size=10, bold=False):
    result = page.insert_textbox(rect, text, fontsize=size, fontname="hebo" if bold else "helv", lineheight=1.25)
    if result < 0:
        raise ValueError(f"Sample text does not fit: {text[:50]}")


def make_sample(destination=OUTPUT):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.draw_line((44, 30), (551, 30), color=(.64,.72,.65), width=.5)
        page.insert_text((44, 23), "PAPERBRIDGE / SYNTHETIC LAYOUT TEST / NOT A PUBLISHED PAPER", fontsize=7, color=(.5,.55,.5))
        write(page, (44, 49, 550, 103), "Bayesian inference of supernova light curves", 20, True)
        write(page, (44, 108, 550, 137), "A synthetic document for testing scientific PDF translation", 10)
        write(page, (44, 151, 550, 169), "Abstract", 11, True)
        write(page, (44, 175, 550, 232), "We present a synthetic example of Bayesian inference for supernova light curves. The model includes a circumstellar medium and reports a confidence interval. The example is designed to test layout preservation; it does not represent an observational result.", 10)
        write(page, (44, 258, 285, 280), "1. Introduction", 12, True)
        write(page, (44, 291, 285, 385), "Supernova light curves provide information about the progenitor and its circumstellar medium. In this example, the effective temperature is 6000 K and the redshift is 0.05. These values are synthetic. A correlation does not necessarily imply a causal relationship.", 10)
        write(page, (44, 404, 285, 432), "2. Methods", 12, True)
        write(page, (44, 441, 285, 515), "We estimate the posterior distribution using Bayesian inference. The prior distribution is specified before fitting the data. The confidence interval is 95%, while the signal-to-noise ratio is 12.5 [1].", 10)
        # Display formula remains in the original PDF, with its font and position.
        page.insert_text((83, 544), "L = 4 pi R^2 sigma T^4     (1)", fontsize=11, fontname="cour")
        write(page, (44, 565, 285, 635), "The luminosity depends on the effective temperature. The simplified model may underestimate the systematic uncertainty. This limitation should be considered when interpreting the results.", 10)
        # Raster scientific figure with labels, preserved bit-for-bit by exports.
        with fitz.open() as chart:
            cp = chart.new_page(width=450,height=280)
            cp.draw_rect((0,0,450,280),color=None,fill=(.97,.985,.965))
            cp.draw_line((50,230),(425,230),color=(.3,.38,.3))
            cp.draw_line((50,25),(50,230),color=(.3,.38,.3))
            points=[(50,205),(110,165),(180,75),(250,55),(315,100),(370,140),(420,170)]
            cp.draw_polyline(points,color=(.25,.52,.39),width=3)
            for point in points: cp.draw_circle(point,3,color=None,fill=(.25,.52,.39))
            cp.insert_text((166,260),"Time (days)",fontsize=13)
            cp.insert_text((70,30),"Synthetic light curve",fontsize=13)
            cp.insert_text((12,130),"Flux",fontsize=12,rotate=90)
            raster=cp.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes("png")
        page.insert_image((310,258,550,408),stream=raster)
        write(page,(310,418,550,462),"Figure 1. Synthetic light curve used to test image preservation. Image labels remain in English.",9)
        write(page,(310,484,550,508),"Table 1. Synthetic model parameters",10,True)
        x_positions=[310,430,550]
        y_positions=[518,544,570,596,622]
        for x in x_positions: page.draw_line((x,518),(x,622),color=(.48,.55,.45),width=.6)
        for y in y_positions: page.draw_line((310,y),(550,y),color=(.48,.55,.45),width=.6)
        rows=[("Parameter","Value"),("Temperature","6000 K"),("Redshift","0.05"),("Confidence interval","95%")]
        for row_index,row in enumerate(rows):
            for col_index,value in enumerate(row):
                page.insert_text((x_positions[col_index]+6,y_positions[row_index]+17),value,fontsize=9,fontname="hebo" if row_index==0 else "helv")
        write(page,(310,644,550,675),"3. Discussion",12,True)
        write(page,(310,680,550,746),"The results suggest that a larger sample may improve the precision. However, the available evidence is insufficient to establish causation. All values in this document are illustrative.",10)
        write(page,(44,679,285,701),"References",11,True)
        write(page,(44,709,285,746),"[1] Example Author. Synthetic reference for a layout test. 2026. Not a real citation.",9)
        page.insert_text((290,811),"1",fontsize=9,color=(.5,.55,.5))
        # Analysis must resume references only within normal reading order. Keep test
        # references at bottom-left, after all earlier semantic content on the page.
        doc.set_metadata({"title":"Synthetic SCI layout test", "author":"PaperBridge test fixture", "subject":"Not a published scientific paper"})
        doc.save(destination,deflate=True)
    return destination


if __name__ == "__main__":
    print(make_sample(Path(sys.argv[1]) if len(sys.argv)>1 else OUTPUT))
