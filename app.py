import json, random, hashlib, time
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="博学考试刷题 · 升级UI版", page_icon="📘", layout="wide")

st.markdown("""
<style>
:root { --pri:#3b82f6; --ok:#10b981; --err:#ef4444; --ink:#0f172a; --muted:#64748b; }
.block-container { padding-top: 1.6rem; padding-bottom: 2.4rem; }
h1,h2,h3 { letter-spacing:.2px; }
.progress-wrap {display:flex; align-items:center; gap:.6rem; margin:.6rem 0 1rem;}
.progress-bar {flex:1; height:10px; background:#e5e7eb; border-radius:999px; overflow:hidden;}
.progress-bar > span {display:block; height:100%; background:var(--pri);}
.q-card {background:#fff; border:1px solid #e5e7eb; border-radius:16px; padding:18px;}
.q-title {font-size:1.05rem; line-height:1.65; color:var(--ink);}
.stRadio > div { display:grid !important; grid-template-columns: 1fr 1fr; gap:12px; }
.stRadio [role="radio"] { 
  border:1px solid #e5e7eb; border-radius:14px; padding:14px 14px; background:#fff; 
  transition:.15s ease; box-shadow:none;
}
.stRadio [role="radio"]:hover { border-color:#cbd5e1; transform: translateY(-1px); }
.stRadio [role="radio"][aria-checked="true"] { 
  border-color: var(--pri); box-shadow: 0 0 0 3px rgba(59,130,246,.16);
}
.stRadio [role="radio"] p { margin:0; color:#0f172a; }
.btn-row { display:flex; gap:.6rem; justify-content:flex-end; margin-top:.6rem; }
.btn {padding:.6rem .9rem; border-radius:12px; border:1px solid #e5e7eb; background:#fff; cursor:pointer;}
.btn.prim {background:var(--pri); color:#fff; border-color:var(--pri);}
.btn.ghost {background:#fff;}
.timer-chip {position:fixed; right:16px; top:16px; z-index:50; background:#111827; color:#fff;
  padding:8px 12px; border-radius:999px; font-variant-numeric: tabular-nums; font-weight:600;}
.alert-ok {border-left:4px solid var(--ok); background:#ecfdf5; padding:10px 12px; border-radius:10px;}
.alert-err {border-left:4px solid var(--err); background:#fef2f2; padding:10px 12px; border-radius:10px;}
</style>
""", unsafe_allow_html=True)

def qkey(q: dict) -> str:
    raw = f"{q.get('chapter','')}|{q.get('section','')}|{q.get('question','')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def is_mcq(q: dict) -> bool:
    return isinstance(q.get("options"), list) and len(q["options"]) >= 2

def normalize_q(q: dict) -> dict:
    q = dict(q)
    q.setdefault("chapter","")
    q.setdefault("section","")
    q.setdefault("type","mcq" if is_mcq(q) else "qa")
    q.setdefault("difficulty",3)
    q.setdefault("tags",[])
    q.setdefault("answer","")
    return q

@st.cache_data
def load_questions():
    with open("questions.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [normalize_q(x) for x in data]

@st.cache_data
def load_blueprint():
    try:
        with open("blueprint.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

ALL_QUESTIONS = load_questions()
BLUEPRINT = load_blueprint()

def ui_header(current:int, total:int, title_html:str):
    pct = 0 if total == 0 else int(current/total*100)
    st.markdown(
        f"""
        <div class='progress-wrap'>
          <div class='progress-bar'><span style='width:{pct}%;'></span></div>
          <div style='color:#64748b;font-size:.92rem'>{current}/{total}</div>
        </div>
        <div class='q-card'><div class='q-title'>{title_html}</div></div>
        """, unsafe_allow_html=True
    )

def _init_session():
    ss = st.session_state
    ss.setdefault("pool", [])
    ss.setdefault("idx", 0)
    ss.setdefault("correct", 0)
    ss.setdefault("attempts", 0)
    ss.setdefault("history", [])
    ss.setdefault("wrong_map", {})
    ss.setdefault("exam_running", False)
    ss.setdefault("exam_start_ts", None)
    ss.setdefault("exam_duration_sec", 0)
    ss.setdefault("exam_pool", [])
    ss.setdefault("exam_answers", {})
    ss.setdefault("exam_submitted", False)
    ss.setdefault("exam_report", None)
    ss.setdefault("answered", False)       # 当前题是否已作答
    ss.setdefault("auto_advance", False)   # 提交后是否自动跳到下一题
_init_session()

st.title("📘 博学考试刷题 · 升级UI版")
st.caption("练习模式 + 考试模式（计时/合格线）。替换 questions.json 即可更新题库；可选 blueprint.json 指导抽题。")

mode_top = st.sidebar.radio("运行模式", ["练习模式", "考试模式"], index=0)

chapters = sorted({q.get("chapter","") for q in ALL_QUESTIONS if q.get("chapter")})
sections_by_ch = {}
for q in ALL_QUESTIONS:
    ch, sec = q.get("chapter",""), q.get("section","")
    if ch:
        sections_by_ch.setdefault(ch, set()).add(sec)

chap_sel = st.sidebar.multiselect("章节", options=chapters, default=chapters)
sec_options = sorted({s for ch in chap_sel for s in sections_by_ch.get(ch, set()) if s})
sec_sel = st.sidebar.multiselect("小节（可选）", options=sec_options, default=sec_options)

def filter_by_chapter_section(q):
    in_ch = (not chap_sel) or (q.get("chapter","") in chap_sel)
    in_sec = (not sec_sel) or (q.get("section","") in sec_sel) or (not q.get("section"))
    return in_ch and in_sec

def build_practice_pool(limit=50):
    pool = [q for q in ALL_QUESTIONS if filter_by_chapter_section(q) and is_mcq(q)]
    random.shuffle(pool)
    return pool[:min(limit, len(pool))]

def reset_practice(limit):
    st.session_state.pool = build_practice_pool(limit)
    st.session_state.idx = 0
    st.session_state.correct = 0
    st.session_state.attempts = 0
    st.session_state.history = []
    st.session_state.answered = False

if mode_top == "练习模式":
    st.header("🧪 练习模式")

    st.sidebar.markdown("**交互方式**")
    st.session_state.auto_advance = st.sidebar.checkbox(
        "提交后自动跳到下一题", value=st.session_state.get("auto_advance", False)
    )

    limit = st.sidebar.slider("每轮题量", 5, 300, min(50, len(ALL_QUESTIONS)))
    if not st.session_state.pool:
        reset_practice(limit)

    if st.sidebar.button("🔄 重新抽题"):
        reset_practice(limit)

    pool = st.session_state.pool
    if not pool:
        st.warning("当前筛选下没有题目。请调整筛选或更新题库。")
    else:
        i = st.session_state.idx
        q = pool[i]
        qid = qkey(q)

        ui_header(i + 1, len(pool), f"**题目：** {q.get('question','')}")

        opts = list(q["options"])
        rng = random.Random(qid); rng.shuffle(opts)
        prev = st.session_state.get(f"sel_{qid}", opts[0])
        sel = st.radio(" ", opts, index=opts.index(prev) if prev in opts else 0,
                       label_visibility="collapsed", key=f"sel_{qid}")

        cols = st.columns(3)
        with cols[0]:
            skip_clicked = st.button("⬅️ 跳过本题", use_container_width=True)
        with cols[2]:
            submit_clicked = st.button("✅ 提交答案", type="primary", use_container_width=True)

        if skip_clicked:
            st.session_state.answered = False
            st.session_state.idx = min(i + 1, len(pool) - 1)
            st.rerun()

        if submit_clicked:
            st.session_state.attempts += 1
            if sel == q.get("answer",""):
                st.session_state.correct += 1
                st.markdown("<div class='alert-ok'>✅ 回答正确！</div>", unsafe_allow_html=True)
                st.session_state.wrong_map.pop(qid, None)
            else:
                st.markdown(f"<div class='alert-err'>❌ 回答错误。正确答案：{q.get('answer','')}</div>", unsafe_allow_html=True)
                st.session_state.wrong_map[qid] = q
            st.session_state.history.append((qid, sel == q.get("answer","")))

            if st.session_state.auto_advance:
                st.session_state.answered = False
                st.session_state.idx = min(i + 1, len(pool) - 1)
                st.rerun()
            else:
                st.session_state.answered = True

        if (not st.session_state.auto_advance) and st.session_state.answered:
            if st.button("➡️ 下一题", use_container_width=True):
                st.session_state.answered = False
                st.session_state.idx = min(i + 1, len(pool) - 1)
                st.rerun()

    st.divider()
    st.subheader("📊 成绩面板")
    acc = (st.session_state.correct / st.session_state.attempts * 100) if st.session_state.attempts else 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ 正确题数", st.session_state.correct)
    c2.metric("📝 已作答", st.session_state.attempts)
    c3.metric("🎯 正确率", f"{acc:.1f}%")

else:
    st.header("📝 考试模式")
    ss = st.session_state
    exam_minutes = st.sidebar.number_input("考试时长（分钟）", min_value=5, max_value=240, value=60, step=5)
    pass_line = st.sidebar.number_input("合格线（百分制）", min_value=0, max_value=100, value=60, step=1)

    def build_exam_pool():
        pool = [q for q in ALL_QUESTIONS if is_mcq(q) and filter_by_chapter_section(q)]
        random.shuffle(pool)
        return pool[:min(100, len(pool))]

    if not ss.exam_running and not ss.exam_submitted:
        st.info("点击下方按钮开始考试。开始后会启动倒计时，期间不显示对错；交卷后显示分数与报告。")
        if st.button("▶️ 开始考试"):
            ss.exam_pool = build_exam_pool()
            ss.exam_running = True
            ss.exam_submitted = False
            ss.exam_answers = {}
            ss.exam_report = None
            ss.exam_duration_sec = int(exam_minutes) * 60
            ss.exam_start_ts = time.time()
            ss.idx = 0
            st.rerun()

    if ss.exam_running and not ss.exam_submitted:
        remaining = ss.exam_duration_sec - int(time.time() - ss.exam_start_ts)
        if remaining <= 0:
            ss.exam_running = False
            ss.exam_submitted = True
        m, s = divmod(max(0, remaining), 60)
        st.markdown(f"<div class='timer-chip'>⏳ {m:02d}:{s:02d}</div>", unsafe_allow_html=True)

        pool = ss.exam_pool
        if not pool:
            st.error("没有可用试题。")
        else:
            q = pool[ss.idx]
            qid = qkey(q)

            ui_header(ss.idx + 1, len(pool), f"**题目：** {q.get('question','')}")

            opts = list(q["options"])
            rng = random.Random(qid); rng.shuffle(opts)
            prev_sel = ss.exam_answers.get(qid, opts[0])
            sel = st.radio(" ", opts, index=opts.index(prev_sel) if prev_sel in opts else 0,
                           label_visibility="collapsed", key=f"exam_sel_{qid}")
            ss.exam_answers[qid] = sel

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("⬅️ 上一题", use_container_width=True) and ss.idx > 0:
                    ss.idx -= 1; st.rerun()
            with c2:
                if st.button("➡️ 下一题", use_container_width=True) and ss.idx < len(pool)-1:
                    ss.idx += 1; st.rerun()
            with c3:
                if st.button("📝 交卷", type="primary", use_container_width=True):
                    ss.exam_running = False
                    ss.exam_submitted = True

    if ss.exam_submitted:
        pool = ss.exam_pool
        ans = ss.exam_answers
        total = len(pool)
        correct = 0
        wrong_detail = []
        for q in pool:
            qid = qkey(q)
            sel = ans.get(qid, None)
            ok = (sel == q.get("answer",""))
            if ok: correct += 1
            else:
                wrong_detail.append({
                    "question": q.get("question",""),
                    "selected": sel,
                    "answer": q.get("answer",""),
                    "chapter": q.get("chapter",""),
                    "section": q.get("section",""),
                })
                st.session_state.wrong_map[qid] = q
        score = round(correct / total * 100, 1) if total else 0.0
        passed = score >= pass_line

        st.success(f"🎯 成绩：{score} 分（{'通过' if passed else '未通过'}，合格线 {pass_line} 分）")
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ 正确题数", correct)
        c2.metric("❌ 错题数", len(wrong_detail))
        c3.metric("📝 总题数", total)

        with st.expander("📄 错题明细"):
            for i, item in enumerate(wrong_detail, 1):
                st.markdown(f"**{i}. {item['question']}**")

        report = {
            "score": score, "passed": passed, "total": total, "correct": correct,
            "wrong": len(wrong_detail), "timestamp": datetime.now().isoformat(timespec="seconds")
        }
        st.download_button(
            "⬇️ 下载考试报告（JSON）",
            data=json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="exam_report.json",
            mime="application/json"
        )
        if st.button("🔁 重新开始新考试"):
            ss.exam_running = False
            ss.exam_submitted = False
            ss.exam_report = None
            ss.exam_answers = {}
            ss.exam_pool = []
            st.rerun()
