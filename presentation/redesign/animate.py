"""Adds entrance animations and a fade transition to a pptxgenjs deck.

Objects whose name starts with "A<step>|" (fade + rise) or "A<step>w|" (wipe from left) enter automatically after
the slide appears, staggered by step. Everything else is static. Usage: python animate.py in.pptx out.pptx
"""
import re
import shutil
import sys
import zipfile

from lxml import etree

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"p": P, "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
NAME = re.compile(r"^A(\d+)(w?)\|")

STAGGER_MS = 130   # gap between steps
DUR_MS = 450       # each entrance
COVER_EMBLEM_MS = 1100


def effect_xml(ids, spid, delay, kind, dur, first):
    node = "afterEffect" if first else "withEffect"
    vis = (f'<p:set><p:cBhvr><p:cTn id="{next(ids)}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
           f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
           f'<p:to><p:strVal val="visible"/></p:to></p:set>')
    if kind == "wipe":
        preset, sub = 22, 8
        body = (f'<p:animEffect transition="in" filter="wipe(left)"><p:cBhvr><p:cTn id="{next(ids)}" dur="{dur}"/>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>')
    else:  # gentle fade with a small upward drift
        preset, sub = 42, 0
        body = (f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{next(ids)}" dur="{dur}"/>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
                f'<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="{next(ids)}" dur="{dur}" decel="100000" fill="hold"/>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>ppt_y</p:attrName></p:attrNameLst></p:cBhvr>'
                f'<p:tavLst><p:tav tm="0"><p:val><p:strVal val="#ppt_y+0.02"/></p:val></p:tav>'
                f'<p:tav tm="100000"><p:val><p:strVal val="#ppt_y"/></p:val></p:tav></p:tavLst></p:anim>')
    return (f'<p:par><p:cTn id="{next(ids)}" presetID="{preset}" presetClass="entr" presetSubtype="{sub}" fill="hold" grpId="0" nodeType="{node}">'
            f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{vis}{body}</p:childTnLst></p:cTn></p:par>')


def counter(start):
    n = start
    while True:
        yield n
        n += 1


def animate_slide(xml: bytes, is_cover: bool) -> bytes:
    root = etree.fromstring(xml)
    if root.find("p:timing", NS) is not None or root.find("p:transition", NS) is not None:
        raise SystemExit("slide already has timing or a transition; refusing to overwrite")
    targets = []  # (step, kind, spid, has_text)
    for cnv in root.iter(f"{{{P}}}cNvPr"):
        m = NAME.match(cnv.get("name", ""))
        if not m:
            continue
        shape = cnv.getparent().getparent()
        has_text = shape.tag == f"{{{P}}}sp" and shape.find("p:txBody", NS) is not None
        targets.append((int(m.group(1)), "wipe" if m.group(2) else "rise", cnv.get("id"), has_text))
        cnv.set("name", cnv.get("name")[m.end():])  # clean names in PowerPoint's Selection Pane
    if targets:
        targets.sort(key=lambda t: t[0])
        ids = counter(5)
        effects = []
        for i, (step, kind, spid, _) in enumerate(targets):
            if is_cover and step == 0:
                delay, dur = 0, COVER_EMBLEM_MS
            else:
                delay, dur = 150 + (step - (1 if is_cover else 1)) * STAGGER_MS, DUR_MS
            effects.append(effect_xml(ids, spid, max(0, delay), kind, dur, first=(i == 0)))
        bld = "".join(f'<p:bldP spid="{spid}" grpId="0" animBg="1"/>' for _, _, spid, t in targets if t)
        timing = (
            f'<p:timing xmlns:p="{P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
            '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
            '<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
            f'<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>{"".join(effects)}</p:childTnLst></p:cTn></p:par>'
            '</p:childTnLst></p:cTn></p:par>'
            '</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
            '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>'
            '</p:childTnLst></p:cTn></p:par></p:tnLst>'
            + (f"<p:bldLst>{bld}</p:bldLst>" if bld else "") + "</p:timing>"
        )
    else:
        timing = None
    transition = etree.fromstring(f'<p:transition xmlns:p="{P}" spd="med"><p:fade/></p:transition>')
    anchor = root.find("p:clrMapOvr", NS)
    if anchor is None:
        anchor = root.find("p:cSld", NS)
    idx = list(root).index(anchor) + 1
    root.insert(idx, transition)
    if timing:
        root.insert(idx + 1, etree.fromstring(timing))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def main(src, dst):
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            m = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", item.filename)
            if m:
                data = animate_slide(data, is_cover=(m.group(1) == "1"))
            zout.writestr(item, data)
    shutil.move(tmp, dst)
    print("animated", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
