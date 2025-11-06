
import json, random, hashlib, time
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="博学考试刷题 · 升级版", page_icon="📘", layout="wide")

def qkey(q: dict) -> str:
    raw = f"{q.get('chapter','')}|{q.get('section','')}|{q.get('question','')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def is_mcq(q: dict) -> bool:
    return isinstance(q.get("options"), list) and len(q["options"]) >= 2

def q_type(q: dict) -> str:
    t = q.get("type")
    if t in {"mcq"}: return t
    return "mcq" if is_mcq(q) else "qa"

@st.cache_data
def load_questions():
    try:
        with open("questions.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for q in data:
                q.setdefault("chapter", "")
                q.setdefault("section", "")
                q.setdefault("type", "mcq" if is_mcq(q) else "qa")
                q.setdefault("difficulty", 3)
                q.setdefault("tags", [])
                q.setdefault("answer", "")
            return data
    except Exception as e:
        st.error(f"题库加载失败：{e}")
        return []

@st.cache_data
def load_blueprint():
    try:
        with open("blueprint.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

ALL_QUESTIONS = load_questions()
BLUEPRINT = load_blueprint()

st.title("📘 博学考试刷题 · 升级版")
st.caption("练习模式 + 考试模式（计时/合格线/蓝图规则） + 错题加权抽题。替换 questions.json 即可更新题库，可选 blueprint.json 配题。")

# ---------------- Sidebar ---------------- #
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

if mode_top == "练习模式":
    practice_tab = st.sidebar.selectbox("题型模式", ["全部题型", "仅选择题"])
    shuffle_options = st.sidebar.checkbox("随机打乱选项", value=True)
    weighted_wrong = st.sidebar.checkbox("错题加权抽题（错过的题优先）", value=True)
    limit = st.sidebar.slider("每轮题量", 5, 300, min(30, len(ALL_QUESTIONS)))
else:
    st.sidebar.markdown("### 考试参数")
    exam_minutes = st.sidebar.number_input("考试时长（分钟）", min_value=5, max_value=240, value=60, step=5)
    pass_line = st.sidebar.number_input("合格线（百分制）", min_value=0, max_value=100, value=60, step=1)
    use_blueprint = st.sidebar.checkbox("使用 blueprint.json 抽题（若不存在将自动忽略）", value=True)

def _init_session():
    ss = st.session_state
    ss.setdefault("pool", [])
    ss.setdefault("idx", 0)
    ss.setdefault("correct", 0)
    ss.setdefault("attempts", 0)
    ss.setdefault("history", [])
    ss.setdefault("wrong_map", {})
    ss.setdefault("mcq_choice", {})
    ss.setdefault("exam_running", False)
    ss.setdefault("exam_start_ts", None)
    ss.setdefault("exam_duration_sec", 0)
    ss.setdefault("exam_pool", [])
    ss.setdefault("exam_answers", {})
    ss.setdefault("exam_submitted", False)
    ss.setdefault("exam_report", None)
_init_session()

def filter_by_chapter_section(q):
    in_ch = (not chap_sel) or (q.get("chapter","") in chap_sel)
    in_sec = (not sec_sel) or (q.get("section","") in sec_sel) or (not q.get("section"))
    return in_ch and in_sec

def build_practice_pool():
    pool = [q for q in ALL_QUESTIONS if filter_by_chapter_section(q)]
    if practice_tab == "仅选择题":
        pool = [q for q in pool if is_mcq(q)]
    if st.session_state.get("wrong_map") and st.sidebar.checkbox("仅刷错题", value=False):
        pool = [q for q in pool if qkey(q) in st.session_state.wrong_map]
    if st.session_state.get("wrong_map") and st.sidebar.checkbox("优先错题", value=True):
        weights = []
        for q in pool:
            w = 1.0 + (4.0 if qkey(q) in st.session_state.wrong_map else 0.0)
            weights.append(w)
        if len(pool) > 0:
            k = min(limit, len(pool))
            chosen_idx = random.choices(range(len(pool)), weights=weights, k=k*3)
            seen=set(); picked=[]
            for i in chosen_idx:
                if len(picked) >= k: break
                if i not in seen:
                    seen.add(i); picked.append(pool[i])
            pool = picked
    else:
        random.shuffle(pool)
        pool = pool[:limit]
    return pool

def reset_practice():
    st.session_state.pool = build_practice_pool()
    st.session_state.idx = 0
    st.session_state.correct = 0
    st.session_state.attempts = 0
    st.session_state.history = []
    st.session_state.mcq_choice = {}

def render_question_mcq(q, give_feedback=True, shuffle=True, store_key_prefix=""):
    qid = qkey(q)
    options = list(q["options"])
    rng = random.Random(qid)
    if shuffle: rng.shuffle(options)
    default = st.session_state.mcq_choice.get(qid, options[0])
    selected = st.radio("请选择一个答案：", options, index=options.index(default) if default in options else 0, key=f"{store_key_prefix}radio_{qid}")
    st.session_state.mcq_choice[qid] = selected
    col1, col2 = st.columns(2)
    with col1:
        if st.button("提交答案", key=f"{store_key_prefix}submit_{qid}"):
            if give_feedback:
                st.session_state.attempts += 1
                is_right = (selected == q.get("answer",""))
                if is_right:
                    st.session_state.correct += 1
                    st.success("回答正确！🎉")
                    st.session_state.wrong_map.pop(qid, None)
                else:
                    st.error(f"错误。正确答案：{q.get('answer','')}")
                    st.session_state.wrong_map[qid] = q
                st.session_state.history.append((qid, is_right))
            return True
    with col2:
        if st.button("跳过本题", key=f"{store_key_prefix}skip_{qid}"):
            return True
    return False

if mode_top == "练习模式":
    st.header("🧪 练习模式")
    if not st.session_state.pool:
        reset_practice()
    st.sidebar.button("🔄 重新抽题", on_click=reset_practice)

    pool = st.session_state.pool
    if not pool:
        st.warning("当前筛选下没有题目。请调整筛选或更新题库。")
    else:
        q = pool[st.session_state.idx]
        st.subheader(f"📍 第 {st.session_state.idx + 1} / {len(pool)} 题")
        st.markdown(f"**题目：** {q.get('question','')}")
        moved = False
        if is_mcq(q):
            moved = render_question_mcq(q, give_feedback=True, shuffle=True)
        else:
            st.info("本题不是选择题。")
        if moved:
            st.session_state.idx = min(st.session_state.idx + 1, len(pool) - 1)

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

    def sample_by_blueprint(rules, total):
        picked = []; used = set()
        for rule in rules:
            cnt = int(rule.get("count", 0))
            if cnt <= 0: continue
            def rf(q):
                if not is_mcq(q): return False
                if not filter_by_chapter_section(q): return False
                ok = True
                if "chapter" in rule and rule["chapter"]:
                    ok = ok and (q.get("chapter","") in rule["chapter"] if isinstance(rule["chapter"], list) else q.get("chapter","")==rule["chapter"])
                if "section" in rule and rule["section"]:
                    ok = ok and (q.get("section","") in rule["section"] if isinstance(rule["section"], list) else q.get("section","")==rule["section"])
                if "tags" in rule and rule["tags"]:
                    ok = ok and (set(rule["tags"]) & set(q.get("tags",[])))
                if "difficulty" in rule and isinstance(rule["difficulty"], list) and len(rule["difficulty"])==2:
                    d = int(q.get("difficulty",3)); lo, hi = rule["difficulty"]
                    ok = ok and (lo <= d <= hi)
                return ok
            cand = [q for q in ALL_QUESTIONS if rf(q)]
            random.shuffle(cand)
            for q in cand:
                qid = qkey(q)
                if qid in used: continue
                picked.append(q); used.add(qid)
                if len([1 for r in rules[:rules.index(rule)+1]]) and len(picked) >= sum(r.get("count",0) for r in rules[:rules.index(rule)+1]):
                    break
        if total and len(picked) < total:
            remain = [q for q in ALL_QUESTIONS if is_mcq(q) and filter_by_chapter_section(q) and qkey(q) not in used]
            random.shuffle(remain)
            picked += remain[:max(0, total - len(picked))]
        return picked[:total] if total else picked

    def build_exam_pool():
        if st.sidebar.checkbox("使用 blueprint.json 抽题（若不存在自动忽略）", value=True) and BLUEPRINT:
            total = int(BLUEPRINT.get("total", 100))
            rules = BLUEPRINT.get("rules", [])
            pool = sample_by_blueprint(rules, total)
            if not pool:
                pool = [q for q in ALL_QUESTIONS if is_mcq(q) and filter_by_chapter_section(q)]
                random.shuffle(pool); pool = pool[:total]
        else:
            pool = [q for q in ALL_QUESTIONS if is_mcq(q) and filter_by_chapter_section(q)]
            random.shuffle(pool); pool = pool[:min(100, len(pool))]
        return pool

    if not ss.exam_running and not ss.exam_submitted:
        st.info("点击下方按钮开始考试。开始后会启动倒计时，期间不显示对错；交卷后显示分数与报告。")
        if st.button("▶️ 开始考试"):
            ss.exam_pool = build_exam_pool()
            ss.exam_running = True
            ss.exam_submitted = False
            ss.exam_answers = {}
            ss.exam_report = None
            ss.exam_duration_sec = st.sidebar.number_input("考试时长（分钟）", min_value=5, max_value=240, value=60, step=5) * 60
            ss.exam_start_ts = time.time()
            ss.idx = 0
            st.experimental_rerun()

    if ss.exam_running and not ss.exam_submitted:
        remaining = ss.exam_duration_sec - int(time.time() - ss.exam_start_ts)
        if remaining <= 0:
            ss.exam_running = False
            ss.exam_submitted = True
        m, s = divmod(max(0, remaining), 60)
        st.warning(f"⏳ 剩余时间：{m:02d}:{s:02d}")

        pool = ss.exam_pool
        if not pool:
            st.error("没有可用试题，请检查题库或蓝图规则。")
        else:
            q = pool[ss.idx]
            qid = qkey(q)
            st.subheader(f"📍 第 {ss.idx + 1} / {len(pool)} 题")
            st.markdown(f"**题目：** {q.get('question','')}")

            options = list(q["options"])
            rng = random.Random(qid); rng.shuffle(options)
            prev_sel = ss.exam_answers.get(qid, options[0])
            sel = st.radio("请选择：", options, index=options.index(prev_sel) if prev_sel in options else 0, key=f"exam_radio_{qid}")
            ss.exam_answers[qid] = sel

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("⬅️ 上一题") and ss.idx > 0:
                    ss.idx -= 1; st.experimental_rerun()
            with c2:
                if st.button("➡️ 下一题") and ss.idx < len(pool)-1:
                    ss.idx += 1; st.experimental_rerun()
            with c3:
                if st.button("📝 交卷"):
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
                    "section": q.get("section","")
                })
                st.session_state.wrong_map[qid] = q
        score = round(correct / total * 100, 1) if total else 0.0
        pass_line = int(BLUEPRINT.get("pass_score", 60)) if BLUEPRINT else 60
        passed = score >= pass_line
        ss.exam_report = {
            "score": score,
            "passed": passed,
            "total": total,
            "correct": correct,
            "wrong": len(wrong_detail),
            "detail": wrong_detail,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }

        st.success(f"🎯 成绩：{score} 分（{'通过' if passed else '未通过'}，合格线 {pass_line} 分）")
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ 正确题数", correct)
        c2.metric("❌ 错题数", len(wrong_detail))
        c3.metric("📝 总题数", total)

        with st.expander("📄 错题明细"):
            for i, item in enumerate(wrong_detail, 1):
                st.markdown(f"**{i}. {item['question']}**")
            st.caption("交卷后错题会加入错题本，在练习模式可优先抽取。")

        st.download_button(
            "⬇️ 下载考试报告（JSON）",
            data=json.dumps(ss.exam_report, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"exam_report_{int(time.time())}.json",
            mime="application/json"
        )

        if st.button("🔁 重新开始新考试"):
            ss.exam_running = False
            ss.exam_submitted = False
            ss.exam_report = None
            ss.exam_answers = {}
            ss.exam_pool = []
            st.experimental_rerun()
