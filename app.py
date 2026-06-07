import json
from pathlib import Path
import streamlit as st

BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data.json"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DATA = json.load(f)

st.set_page_config(page_title="タイプ判定", page_icon="🐦", layout="centered")

st.title("🐦 タイプ判定")
st.write(DATA["title"])
st.caption("各質問について、最も近いものを選んでください。最後に、最も得点が高いタイプを1つだけ表示します。")

with st.form("diagnosis_form"):
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
    unanswered = [i + 1 for i, a in enumerate(answers) if a is None]
    if unanswered:
        st.error(f"未回答があります：{', '.join(map(str, unanswered))}番")
    else:
        scores = {type_name: 0 for type_name in DATA["types"].keys()}

        for q, selected_label in zip(DATA["questions"], answers):
            selected = next(c for c in q["choices"] if c["label"] == selected_label)
            for type_name, point in selected["scores"].items():
                scores[type_name] += int(point)

        max_score = max(scores.values())
        candidates = [t for t, s in scores.items() if s == max_score]

        # 同点の場合は tie_break_order の順で1つに決める
        result_type = next(t for t in DATA["tie_break_order"] if t in candidates)
        result = DATA["types"][result_type]

        st.divider()
        st.subheader(result["display"])

        img_path = BASE_DIR / "images" / result["image"]
        if img_path.exists():
            st.image(str(img_path), use_container_width=False, width=320)

        st.markdown(result["body"].replace("\n", "  \n"))

        with st.expander("得点を見る"):
            for type_name, score in scores.items():
                max_score_type = DATA.get("max_scores", {}).get(type_name, "")
                suffix = f" / {max_score_type}" if max_score_type != "" else ""
                st.write(f"**{type_name}**：{score}{suffix}")

        if len(candidates) > 1:
            st.caption("※最高点が同点だったため、あらかじめ設定した優先順で1タイプだけ表示しています。")
