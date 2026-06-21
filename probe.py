import sys, pdfplumber

def rows(pdf_path, ytol=3):
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            words.sort(key=lambda w: (round(w["top"]), w["x0"]))
            line = []
            cur = None
            for w in words:
                t = round(w["top"])
                if cur is None or abs(t - cur) <= ytol:
                    line.append(w)
                    cur = t if cur is None else cur
                else:
                    out.append((pno, cur, line))
                    line = [w]
                    cur = t
            if line:
                out.append((pno, cur, line))
    return out

if __name__ == "__main__":
    path = sys.argv[1]
    for pno, y, line in rows(path):
        line.sort(key=lambda w: w["x0"])
        # show x0 of each token to understand columns, plus joined text
        txt = "  ".join(w["text"] for w in line)
        xs = ",".join(str(int(w["x0"])) for w in line)
        print(f"p{pno} y{int(y):4d} | {txt}")
