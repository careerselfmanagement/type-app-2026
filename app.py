import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import streamlit as st

BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data.json"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DATA = json.load(f)

APP_TITLE = DATA.get("app_title", "小川ゼミ版コース診断")
GENDER_OPTIONS = DATA.get("gender_options", {"男性": 0, "女性": 1, "その他": 2})
GPA_OPTIONS = DATA.get("gpa_options", [
    "1.0未満",
    "1.0以上1.5未満",
    "1.5以上2.0未満",
    "2.0以上2.5未満",
    "2.5以上3.0未満",
    "3.0以上3.5未満",
    "3.5以上",
])

st.set_page_config(page_title=APP_TITLE, page_icon="🐦", layout="centered")


def _get_secret_value(*keys):
    for key in keys:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return None


def _get_gspread_client():
    try:
        import gspread
    except Exception:
        return None, "gspreadがインストールされていません。"

    service_account_info = _get_secret_value("gcp_service_account", "google_service_account")
    if service_account_info is None:
        try:
            service_account_info = st.secrets["google"]["service_account"]
        except Exception:
            service_account_info = None

    if service_account_info is None:
        return None, "Google Sheets用のSecretsが未設定です。"

    try:
        client = gspread.service_account_from_dict(dict(service_account_info))
        return client, None
    except Exception as e:
        return None, f"Google認証に失敗しました: {e}"


def _count_values(rows, key):
    counts = {}
    for row in rows:
        value = row.get(key, "")
        if value != "":
            counts[value] = counts.get(value, 0) + 1
    return counts


def _write_summary_worksheet(spreadsheet, title, headers, body):
    try:
        ws = spreadsheet.worksheet(title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=200, cols=max(10, len(headers)))
    ws.clear()
    ws.update("A1", [headers] + body, value_input_option="USER_ENTERED")


def update_summary_sheets(spreadsheet):
    try:
        responses = spreadsheet.worksheet("responses")
        rows = responses.get_all_records()
    except Exception:
        return

    total = len(rows)
    _write_summary_worksheet(spreadsheet, "summary", ["項目", "値"], [["総回答数", total]])

    def ratio(n):
        return round(n / total, 4) if total else 0

    result_counts = _count_values(rows, "result_type")
    result_body = [[k, v, ratio(v)] for k, v in sorted(result_counts.items(), key=lambda x: (-x[1], x[0]))]
    _write_summary_worksheet(spreadsheet, "summary_result", ["result_type", "count", "ratio"], result_body)

    gender_counts = _count_values(rows, "gender_label")
    gender_body = [[k, v, ratio(v)] for k, v in sorted(gender_counts.items(), key=lambda x: x[0])]
    _write_summary_worksheet(spreadsheet, "summary_gender", ["gender", "count", "ratio"], gender_body)

    gpa_counts = _count_values(rows, "gpa_bin")
    gpa_body = [[k, gpa_counts.get(k, 0), ratio(gpa_counts.get(k, 0))] for k in GPA_OPTIONS]
    _write_summary_worksheet(spreadsheet, "summary_gpa", ["gpa_bin", "count", "ratio"], gpa_body)

    genders = list(GENDER_OPTIONS.keys())
    cross_gender = []
    for result in sorted(result_counts.keys()):
        row = [result]
        for g in genders:
            row.append(sum(1 for r in rows if r.get("result_type") == result and r.get("gender_label") == g))
        cross_gender.append(row)
    _write_summary_worksheet(spreadsheet, "summary_result_by_gender", ["result_type"] + genders, cross_gender)

    cross_gpa = []
    for result in sorted(result_counts.keys()):
        row = [result]
        for gpa in GPA_OPTIONS:
            row.append(sum(1 for r in rows if r.get("result_type") == result and r.get("gpa_bin") == gpa))
        cross_gpa.append(row)
    _write_summary_worksheet(spreadsheet, "summary_result_by_gpa", ["result_type"] + GPA_OPTIONS, cross_gpa)


def save_response_to_google_sheets(row_dict):
    sheet_url = _get_secret_value("spreadsheet_url", "GOOGLE_SHEET_URL")
    if sheet_url is None:
        try:
            sheet_url = st.secrets["google"]["spreadsheet_url"]
        except Exception:
            sheet_url = None

    if not sheet_url:
        return False, "スプレッドシートURLがSecretsにありません。"

    client, err = _get_gspread_client()
    if err:
        return False, err

    try:
        spreadsheet = client.open_by_url(sheet_url)
        try:
            worksheet = spreadsheet.worksheet("responses")
        except Exception:
            worksheet = spreadsheet.add_worksheet(title="responses", rows=1000, cols=120)

        headers = list(row_dict.keys())
        existing = worksheet.row_values(1)
        if not existing:
            worksheet.append_row(headers, value_input_option="USER_ENTERED")
        elif existing != headers:
            headers = existing + [h for h in headers if h not in existing]
            worksheet.update("1:1", [headers])

        worksheet.append_row([row_dict.get(h, "") for h in headers], value_input_option="USER_ENTERED")
        update_summary_sheets(spreadsheet)
        return True, None
    except Exception as e:
        return False, str(e)


st.title(f"🐦 {APP_TITLE}")
if DATA.get("title"):
    st.write(DATA["title"])

start_img = BASE_DIR / "images" / "start.png"
if start_img.exists():
    st.image(str(start_img), width=180)

st.caption("各質問について、最も近いものを選んでください。最後に、オススメのコースを表示します。")

with st.form("diagnosis_form"):
    st.subheader("基本情報")
    user_id = st.text_input(
        "学籍番号を直接入力してください",
        key="user_id",
    )
    gender_label = st.radio(
        "性別を教えてください",
        list(GENDER_OPTIONS.keys()),
        index=None,
        horizontal=True,
        key="gender",
    )
    gpa_bin = st.selectbox(
        "現状のGPAを選択してください",
        GPA_OPTIONS,
        index=None,
        placeholder="選択してください",
        key="gpa_bin",
    )

    st.divider()
    st.subheader("質問")

    answers = []
    for q in DATA["questions"]:
        labels = [c["label"] for c in q["choices"]]
        choice = st.radio(
            f"{q['id']}. {q['text']}",
            labels,
            index=None,
            horizontal=True,
            key=f"q_{q['id']}",
        )
        answers.append(choice)

    submitted = st.form_submit_button("診断する")

if submitted:
    missing = []
    if gender_label is None:
        missing.append("性別")
    if gpa_bin is None:
        missing.append("GPA")

    unanswered = [i + 1 for i, a in enumerate(answers) if a is None]

    if missing or unanswered:
        msg = []
        if missing:
            msg.append("未選択：" + "、".join(missing))
        if unanswered:
            msg.append(f"未回答：{', '.join(map(str, unanswered))}番")
        st.error(" / ".join(msg))
    else:
        scores = {type_name: 0 for type_name in DATA["types"].keys()}

        for q, selected_label in zip(DATA["questions"], answers):
            selected = next(c for c in q["choices"] if c["label"] == selected_label)
            for type_name, point in selected["scores"].items():
                if type_name in scores:
                    scores[type_name] += int(point)

        uniform_answer = len(set(answers)) == 1
        max_score = max(scores.values())
        candidates = [t for t, s in scores.items() if s == max_score]

        if uniform_answer:
            result_type = "判定不能"
            result = None
        else:
            result_type = next(t for t in DATA["tie_break_order"] if t in candidates)
            result = DATA["types"][result_type]

        now_jst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")
        row = {
            "timestamp_jst": now_jst,
            "user_id": user_id,
            "gender_label": gender_label,
            "gender_code": GENDER_OPTIONS[gender_label],
            "gpa_bin": gpa_bin,
            "result_type": result_type,
            "max_score": max_score,
            "tie_candidates": ",".join(candidates),
            "uniform_answer": "yes" if uniform_answer else "no",
        }
        for type_name, score in scores.items():
            row[f"score_{type_name}"] = score
        for q, a in zip(DATA["questions"], answers):
            row[f"q{q['id']}_text"] = q["text"]
            row[f"q{q['id']}_answer"] = a

        saved, save_error = save_response_to_google_sheets(row)

        st.divider()

        if uniform_answer:
            st.error(DATA.get("invalid_message", "判定不能。真面目に答えましょう。"))
            invalid_img = BASE_DIR / "images" / "invalid.png"
            if invalid_img.exists():
                st.image(str(invalid_img), width=260)
        else:
            st.subheader(result["display"])
            img_path = BASE_DIR / "images" / result["image"]
            if img_path.exists():
                st.image(str(img_path), use_container_width=False, width=320)
            st.markdown(result["body"].replace("\n", "  \n"))
            # if len(candidates) > 1:
            #    st.caption("※最高点が同点だったため、あらかじめ設定した優先順で1タイプだけ表示しています。")

        if saved:
            st.caption("回答を記録しました。")
        else:
            st.warning(f"診断結果は表示できましたが、記録に失敗しました：{save_error}")
