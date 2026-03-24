import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime

# ── COLOURS (matched to original) ────────────────────────────
C_DARK_GREEN  = "1F4E39"  # title/total rows
C_MID_GREEN   = "375623"  # section subtotal
C_LIGHT_GREEN = "E2EFDA"  # budget cells bg
C_DARK_GREY   = "404040"  # column headers
C_MID_GREY    = "808080"
C_LIGHT_GREY  = "F2F2F2"
C_WHITE       = "FFFFFF"
C_BLUE_INPUT  = "0070C0"  # hardcoded admin inputs
C_ORANGE      = "C65911"  # regional totals
C_LIGHT_ORANGE= "FCE4D6"
C_AMBER       = "BF8F00"

MONTHS = [
    ("Jul-25", datetime(2025,7,31)),  ("Aug-25", datetime(2025,8,31)),
    ("Sep-25", datetime(2025,9,30)),  ("Oct-25", datetime(2025,10,31)),
    ("Nov-25", datetime(2025,11,30)), ("Dec-25", datetime(2025,12,31)),
    ("Jan-26", datetime(2026,1,31)),  ("Feb-26", datetime(2026,2,28)),
    ("Mar-26", datetime(2026,3,31)),  ("Apr-26", datetime(2026,4,30)),
    ("May-26", datetime(2026,5,31)),  ("Jun-26", datetime(2026,6,30)),
]

def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def font(bold=False, color="000000", size=10, italic=False, name="Calibri"):
    return Font(name=name, bold=bold, color=color, size=size, italic=italic)

def border(color="AAAAAA"):
    s = Side(style='thin', color=color)
    return Border(left=s, right=s, top=s, bottom=s)

def right_border():
    s = Side(style='medium', color="888888")
    return Border(right=s)

def style_cell(c, bg=None, bold=False, fc="000000", size=10, 
               align="left", wrap=False, num_fmt=None, italic=False):
    if bg:     c.fill = fill(bg)
    c.font     = font(bold=bold, color=fc, size=size, italic=italic)
    c.alignment = Alignment(horizontal=align, vertical='center', wrap_text=wrap)
    if num_fmt: c.number_format = num_fmt

# Column layout:
# A=1  AP Account       B=2  Budget Owner
# C=3  Category         D=4  Country
# E=5  Vendor           F=6  Note/Description
# G=7  FY26 (Act/Budget) H=8  FY26 Budget (admin input)
# I=9  Var Check        J-U (10-21) = Jul-25 to Jun-26 monthly budget

COL_ACCOUNT  = 1
COL_OWNER    = 2
COL_CAT      = 3
COL_COUNTRY  = 4
COL_VENDOR   = 5
COL_NOTE     = 6
COL_FY26_ACT = 7
COL_FY26_BUD = 8
COL_VAR      = 9
COL_M_START  = 10  # Jul-25
COL_M_END    = 21  # Jun-26

def build(output_path, budget_data):
    """
    budget_data: list of dicts with keys:
        account, budget_owner, category, country, vendor, note,
        fy26_budget (total admin budget),
        monthly [12 values: Jul-Jun]
    Rows with country='Total' are section headers (auto-computed).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "APAC"
    ws.sheet_view.showGridLines = False

    # ── COLUMN WIDTHS ─────────────────────────────────────────
    widths = {1:28, 2:18, 3:32, 4:14, 5:22, 6:32, 7:16, 8:16, 9:12}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w
    for i in range(12):
        ws.column_dimensions[get_column_letter(COL_M_START+i)].width = 11

    # ── ROWS 1-3: TITLE ───────────────────────────────────────
    titles = [
        "Marketing Expenses Detail— APAC",
        "Marketing FY26 Budget",
        "Pepperstone Group Limited",
    ]
    for r, t in enumerate(titles, 1):
        ws.merge_cells(f'A{r}:{get_column_letter(COL_M_END)}{r}')
        c = ws.cell(r, 1, t)
        style_cell(c, bg=C_DARK_GREEN if r==1 else None,
                   bold=True, fc=C_WHITE if r==1 else "000000", size=12 if r==1 else 10)
        ws.row_dimensions[r].height = 20 if r==1 else 16

    # ── ROW 4: Units label ────────────────────────────────────
    ws['C4'] = 'AUD $000'; ws['D4'] = 'FY26'
    style_cell(ws['C4'], bg=C_DARK_GREEN, bold=True, fc=C_WHITE, align='center')
    style_cell(ws['D4'], bold=True)
    ws.row_dimensions[4].height = 16

    # ── ROW 5: Current month marker ───────────────────────────
    ws['C5'] = 'Current mth'
    ws['D5'] = datetime(2026, 2, 28)
    ws['D5'].number_format = 'MMM-YY'
    ws.row_dimensions[5].height = 14

    # ── ROW 6: Blank separator ────────────────────────────────
    ws.row_dimensions[6].height = 6

    # ── ROW 7: Section grouping labels ───────────────────────
    ws.merge_cells(f'{get_column_letter(COL_M_START)}7:{get_column_letter(COL_M_END)}7')
    c7 = ws.cell(7, COL_M_START, "Budget — Monthly (Jul 2025 to Jun 2026)")
    style_cell(c7, bg=C_DARK_GREEN, bold=True, fc=C_WHITE, align='center')

    for col in [COL_ACCOUNT, COL_OWNER, COL_CAT, COL_COUNTRY, COL_VENDOR, COL_NOTE,
                COL_FY26_ACT, COL_FY26_BUD, COL_VAR]:
        style_cell(ws.cell(7, col), bg=C_DARK_GREEN, fc=C_WHITE)
    ws.row_dimensions[7].height = 18

    # ── ROW 8: COLUMN HEADERS ─────────────────────────────────
    headers = [
        (COL_ACCOUNT,  "AP- Main Account"),
        (COL_OWNER,    "Budget Owner"),
        (COL_CAT,      "Category"),
        (COL_COUNTRY,  "Country"),
        (COL_VENDOR,   "Vendor"),
        (COL_NOTE,     "Note / Description"),
        (COL_FY26_ACT, "FY26 (Act/Budget)"),
        (COL_FY26_BUD, "FY26 Budget"),
        (COL_VAR,      "Var Check"),
    ]
    for col, lbl in headers:
        c = ws.cell(8, col, lbl)
        style_cell(c, bg=C_DARK_GREY, bold=True, fc=C_WHITE, size=9, align='center', wrap=True)
        c.border = border()

    for i, (lbl, _) in enumerate(MONTHS):
        c = ws.cell(8, COL_M_START+i, lbl)
        style_cell(c, bg="1C6B4A", bold=True, fc=C_WHITE, size=9, align='center')
        c.border = border()
    ws.row_dimensions[8].height = 30

    # ── DATA SECTION ──────────────────────────────────────────
    # Group by category
    from collections import defaultdict, OrderedDict
    cats = OrderedDict()
    for row in budget_data:
        cat = row['category']
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(row)

    SECTION_STYLES = {
        "Performance Marketing":  ("375623", "E8F5E0"),
        "Affiliate":              ("1A4A72", "E0EBF5"),
        "Paid Social":            ("7B5E00", "FFF8DC"),
        "Regional Marketing":     ("6B2C00", "FBE8DC"),
        "AMF1 Activation":        ("3B1F6B", "EEE8FA"),
        "Premium":                ("003B4A", "DCF0F5"),
        "Partner":                ("003B4A", "DCF0F5"),
        "RAF":                    ("3B3B00", "F5F5DC"),
        "Mar Tech":               ("404040", "F5F5F5"),
    }

    current_row = 9
    cat_total_rows = []

    # Grand total row placeholder (row 9 in original = top summary)
    # We'll write it first, then insert data
    GRAND_ROW = 9
    current_row = 10  # data starts at 10

    # Track where each category's total row and data rows are
    cat_row_map = {}  # category -> (total_row, [data_rows])

    for cat, rows in cats.items():
        s_colors = SECTION_STYLES.get(cat, ("404040","F9F9F9"))
        s_bg, d_bg = s_colors

        total_row = current_row
        data_start = current_row + 1
        data_end   = current_row + len(rows)
        cat_row_map[cat] = (total_row, list(range(data_start, data_end+1)))
        cat_total_rows.append(total_row)

        # Section subtotal header row
        for col in range(1, COL_M_END+1):
            style_cell(ws.cell(total_row, col), bg=s_bg, fc=C_WHITE)

        ws.cell(total_row, COL_CAT, cat)
        style_cell(ws.cell(total_row, COL_CAT), bg=s_bg, bold=True, fc=C_WHITE, size=10)

        ws.cell(total_row, COL_COUNTRY, "Total")
        style_cell(ws.cell(total_row, COL_COUNTRY), bg=s_bg, bold=True, fc=C_WHITE)

        # FY26 sum formula
        c = ws.cell(total_row, COL_FY26_ACT)
        c.value = f"=SUM(G{data_start}:G{data_end})"
        style_cell(c, bg=s_bg, bold=True, fc=C_WHITE, num_fmt='#,##0')

        c2 = ws.cell(total_row, COL_FY26_BUD)
        c2.value = f"=SUM(H{data_start}:H{data_end})"
        style_cell(c2, bg=s_bg, bold=True, fc=C_WHITE, num_fmt='#,##0')

        c3 = ws.cell(total_row, COL_VAR)
        c3.value = f"=G{total_row}-H{total_row}"
        style_cell(c3, bg=s_bg, bold=True, fc=C_WHITE, num_fmt='#,##0')

        for i in range(12):
            col = COL_M_START + i
            col_l = get_column_letter(col)
            c = ws.cell(total_row, col)
            c.value = f"=SUM({col_l}{data_start}:{col_l}{data_end})"
            style_cell(c, bg=s_bg, bold=True, fc=C_WHITE, num_fmt='#,##0')
            c.border = border()

        ws.row_dimensions[total_row].height = 18
        current_row += 1

        # Data rows
        for j, row in enumerate(rows):
            is_alt = j % 2 == 0
            row_bg = d_bg if is_alt else C_WHITE

            for col in range(1, COL_M_END+1):
                style_cell(ws.cell(current_row, col), bg=row_bg)

            ws.cell(current_row, COL_ACCOUNT, row.get('account', ''))
            ws.cell(current_row, COL_OWNER,   row.get('budget_owner', ''))
            ws.cell(current_row, COL_CAT,     cat)
            ws.cell(current_row, COL_COUNTRY, row.get('country', ''))
            ws.cell(current_row, COL_VENDOR,  row.get('vendor', ''))
            ws.cell(current_row, COL_NOTE,    row.get('note', ''))

            for col in [COL_ACCOUNT, COL_OWNER, COL_CAT, COL_COUNTRY, COL_VENDOR, COL_NOTE]:
                style_cell(ws.cell(current_row, col), bg=row_bg, size=9)

            # FY26 Act/Budget = sum of monthly
            gl = get_column_letter
            c = ws.cell(current_row, COL_FY26_ACT)
            c.value = f"=SUM({gl(COL_M_START)}{current_row}:{gl(COL_M_END)}{current_row})"
            style_cell(c, bg=row_bg, bold=True, fc="1C4F3C", num_fmt='#,##0')

            # FY26 Budget (admin input — blue)
            c2 = ws.cell(current_row, COL_FY26_BUD)
            c2.value = row.get('fy26_budget', 0)
            style_cell(c2, bg=row_bg, fc=C_BLUE_INPUT, num_fmt='#,##0')

            # Var
            c3 = ws.cell(current_row, COL_VAR)
            c3.value = f"=G{current_row}-H{current_row}"
            style_cell(c3, bg=row_bg, num_fmt='#,##0')

            # Monthly values (blue = admin input)
            monthly = row.get('monthly', [0]*12)
            for i, val in enumerate(monthly):
                col = COL_M_START + i
                c = ws.cell(current_row, col, val if val else 0)
                style_cell(c, bg=row_bg, fc=C_BLUE_INPUT, num_fmt='#,##0')
                c.border = border("DDDDDD")

            ws.row_dimensions[current_row].height = 16
            current_row += 1

    # ── GRAND TOTAL (row 9) ───────────────────────────────────
    gt_refs_g = "+".join([f"G{r}" for r in cat_total_rows])
    gt_refs_h = "+".join([f"H{r}" for r in cat_total_rows])

    for col in range(1, COL_M_END+1):
        style_cell(ws.cell(GRAND_ROW, col), bg=C_DARK_GREEN)

    ws.cell(GRAND_ROW, COL_OWNER, "Budget Owner")
    style_cell(ws.cell(GRAND_ROW, COL_OWNER), bg=C_DARK_GREEN, bold=True, fc=C_WHITE)

    ws.cell(GRAND_ROW, COL_CAT, "Total Marketing")
    style_cell(ws.cell(GRAND_ROW, COL_CAT), bg=C_DARK_GREEN, bold=True, fc=C_WHITE)

    ws.cell(GRAND_ROW, COL_COUNTRY, "Total")
    style_cell(ws.cell(GRAND_ROW, COL_COUNTRY), bg=C_DARK_GREEN, bold=True, fc=C_WHITE)

    c = ws.cell(GRAND_ROW, COL_FY26_ACT)
    c.value = f"={gt_refs_g}"
    style_cell(c, bg=C_DARK_GREEN, bold=True, fc=C_WHITE, num_fmt='#,##0')

    c2 = ws.cell(GRAND_ROW, COL_FY26_BUD)
    c2.value = f"={gt_refs_h}"
    style_cell(c2, bg=C_DARK_GREEN, bold=True, fc=C_WHITE, num_fmt='#,##0')

    c3 = ws.cell(GRAND_ROW, COL_VAR)
    c3.value = f"=G{GRAND_ROW}-H{GRAND_ROW}"
    style_cell(c3, bg=C_DARK_GREEN, bold=True, fc=C_WHITE, num_fmt='#,##0')

    for i in range(12):
        col = COL_M_START + i
        col_l = get_column_letter(col)
        refs = "+".join([f"{col_l}{r}" for r in cat_total_rows])
        c = ws.cell(GRAND_ROW, col)
        c.value = f"={refs}"
        style_cell(c, bg=C_DARK_GREEN, bold=True, fc=C_WHITE, num_fmt='#,##0')
        c.border = border()

    ws.row_dimensions[GRAND_ROW].height = 22

    # ── FREEZE ────────────────────────────────────────────────
    ws.freeze_panes = ws.cell(9, COL_FY26_ACT)

    # ── LEGEND / NOTES at bottom ──────────────────────────────
    note_row = current_row + 2
    ws.merge_cells(f'A{note_row}:{get_column_letter(COL_M_END)}{note_row}')
    notes_cell = ws.cell(note_row, 1)
    notes_cell.value = "Legend:   Blue values = Admin input (budget figures)   |   Green values = Auto-calculated (sum of monthly)   |   Var Check = FY26 Act/Budget minus FY26 Budget input"
    style_cell(notes_cell, italic=True, fc="666666", size=8)

    wb.save(output_path)
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    # ── SAMPLE DATA matching APAC sheet structure ─────────────────
    sample = [
        {"account":"Marketing : Paid Search / YouTube","budget_owner":"APAC Marketing","category":"Performance Marketing","country":"Thailand","vendor":"Google","note":"Google search","fy26_budget":40000,"monthly":[3200,3200,3200,3400,3400,3600,3200,3200,3400,3600,3800,4800]},
        {"account":"Marketing : Paid Search / YouTube","budget_owner":"APAC Marketing","category":"Performance Marketing","country":"Vietnam","vendor":"Google","note":"Google search","fy26_budget":18000,"monthly":[1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500]},
        {"account":"Marketing : Paid Search / YouTube","budget_owner":"APAC Marketing","category":"Performance Marketing","country":"Singapore","vendor":"Google","note":"Google search & PMAX","fy26_budget":60000,"monthly":[5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000]},
        {"account":"Marketing : Paid Search / YouTube","budget_owner":"APAC Marketing","category":"Performance Marketing","country":"Malaysia","vendor":"Google","note":"Google search","fy26_budget":48000,"monthly":[4000,4000,4000,4000,4000,4000,4000,4000,4000,4000,4000,4000]},
        {"account":"Microsoft Ireland Operations","budget_owner":"APAC Marketing","category":"Performance Marketing","country":"APAC","vendor":"Bing","note":"Bing search & display","fy26_budget":44000,"monthly":[3500,3500,3500,3700,3700,3700,3700,3700,3700,4000,4000,4200]},
        {"account":"Marketing : Affiliate","budget_owner":"APAC Marketing","category":"Affiliate","country":"Thailand","vendor":"Affiliate","note":"Thailand CPA & FF","fy26_budget":120000,"monthly":[10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000]},
        {"account":"Marketing : Affiliate","budget_owner":"APAC Marketing","category":"Affiliate","country":"Vietnam","vendor":"Affiliate","note":"Vietnam CPA","fy26_budget":24000,"monthly":[2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000]},
        {"account":"Marketing : Affiliate","budget_owner":"APAC Marketing","category":"Affiliate","country":"Singapore","vendor":"Affiliate","note":"Singapore CPA","fy26_budget":12000,"monthly":[1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000]},
        {"account":"Marketing : Paid Social / YouTube","budget_owner":"APAC Marketing","category":"Paid Social","country":"Thailand","vendor":"Meta","note":"Meta paid social","fy26_budget":36000,"monthly":[3000,3000,3000,3000,3000,3000,3000,3000,3000,3000,3000,3000]},
        {"account":"Marketing : Paid Social / YouTube","budget_owner":"APAC Marketing","category":"Paid Social","country":"Singapore","vendor":"Meta","note":"Meta & Twitter","fy26_budget":24000,"monthly":[2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000]},
        {"account":"Marketing : Paid Social / YouTube","budget_owner":"APAC Marketing","category":"Paid Social","country":"China","vendor":"Baidu/WeChat","note":"CN social platforms","fy26_budget":48000,"monthly":[4000,4000,4000,4000,4000,4000,4000,4000,4000,4000,4000,4000]},
        {"account":"Marketing : Local Brand","budget_owner":"APAC Marketing","category":"Regional Marketing","country":"Thailand","vendor":"Various","note":"Events & sponsorship","fy26_budget":30000,"monthly":[2500,2500,2500,2500,2500,2500,2500,2500,2500,2500,2500,2500]},
        {"account":"Marketing : Local Brand","budget_owner":"APAC Marketing","category":"Regional Marketing","country":"Singapore","vendor":"Various","note":"Events","fy26_budget":18000,"monthly":[1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500]},
        {"account":"Marketing : Local Brand","budget_owner":"APAC Marketing","category":"AMF1 Activation","country":"APAC","vendor":"AMF1","note":"AMF1 race activation","fy26_budget":60000,"monthly":[5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000]},
        {"account":"Marketing : Local Brand","budget_owner":"APAC Marketing","category":"AMF1 Activation","country":"Thailand","vendor":"Various KOL","note":"TH influencers","fy26_budget":24000,"monthly":[2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000]},
        {"account":"Marketing : Premium","budget_owner":"APAC Marketing","category":"Premium","country":"APAC","vendor":"Various","note":"Premium partnerships","fy26_budget":48000,"monthly":[4000,4000,4000,4000,4000,4000,4000,4000,4000,4000,4000,4000]},
        {"account":"Marketing : Partners","budget_owner":"APAC Marketing","category":"Partner","country":"APAC","vendor":"Various","note":"Partner programs","fy26_budget":36000,"monthly":[3000,3000,3000,3000,3000,3000,3000,3000,3000,3000,3000,3000]},
        {"account":"Marketing - Refer a friend","budget_owner":"APAC Marketing","category":"RAF","country":"APAC","vendor":"Internal","note":"Refer a friend program","fy26_budget":24000,"monthly":[2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000]},
        {"account":"Marketing : Marketing technology","budget_owner":"APAC Marketing","category":"Mar Tech","country":"APAC","vendor":"Various","note":"Marketing technology platforms","fy26_budget":84000,"monthly":[7000,7000,7000,7000,7000,7000,7000,7000,7000,7000,7000,7000]},
    ]

    build("/home/claude/APAC_Budget_FY26.xlsx", sample)