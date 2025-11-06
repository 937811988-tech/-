import json, random, hashlib, time
from datetime import datetime
from collections import defaultdict
import streamlit as st

st.set_page_config(page_title="博学 · 全量刷题系统（驾考宝典风格）", page_icon="🚗", layout="wide")

st.markdown("""
<style>
:root { --pri:#3b82f6; --ok:#10b981; --err:#ef4444; --ink:#0f172a; --muted:#64748b; }
.block-container { padding-top: 1.0rem; padding-bottom: 2.4rem; max-width: 1100px; }
h1,h2,h3 { letter-spacing:.2px; }
.progress-wrap {display:flex; align-items:center; gap:.6rem; margin:.6rem 0 1rem;}
.progress-bar {flex:1; height:10px; background:#e5e7eb; border-radius:999px; overflow:hidden;}
.progress-bar > span {display:block; height:100%; background:var(--pri);}
.q-card {background:#fff; border:1px solid #e5e7eb; border-radius:16px; padding:18px;}
.q-title {font-size:1.05rem; line-height:1.65; color:#0f172a;}
.meta { color:#64748b; font-size:.9rem; margin-bottom:.4rem;}
.stRadio > div { display:grid !important; grid-template-columns: 1fr 1fr; gap:12px; }
.stRadio [role="radio"] { border:1px solid #e5e7eb; border-radius:14px; padding:14px; background:#fff; transition:.15s ease; box-shadow:none; }
.stRadio [role="radio"]:hover { border-color:#cbd5e1; transform: translateY(-1px); }
.stRadio [role="radio"][aria-checked="true"] { border-color: var(--pri); box-shadow: 0 0 0 3px rgba(59,130,246,.16); }
.stRadio [role="radio"] p { margin:0; color:#0f172a; }
.timer-chip {position:fixed; right:16px; top:16px; z-index:50; background:#111827; color:#fff;
  padding:8px 12px; border-radius:999px; font-variant-numeric: tabular-nums; font-weight:600;}
.alert-ok {border-left:4px solid var(--ok); background:#ecfdf5; padding:10px 12px; border-radius:10px;}
.alert-err {border-left:4px solid var(--err); background:#fef2f2; padding:10px 12px; border-radius:10px;}
.alert-info {border-left:4px solid #3b82f6; background:#eff6ff; padding:10px 12px; border-radius:10px;}
.badge {display:inline-block; padding:.1rem .5rem; border-radius:999px; background:#eef2ff; color:#3730a3; font-size:.78rem; margin-right:.4rem;}
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
    q.setdefault("explanation","")
    return q

@st.cache_data
def load_questions():
    with open("questions.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [normalize_q(x) for x in data]

ALL_QUESTIONS = load_questions()

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
    ss.setdefault("mode", "顺序练习")
    ss.setdefault("idx", 0)
    ss.setdefault("seq_pool", [])
    ss.setdefault("rand_pool", [])
    ss.setdefault("chap_pool", [])
    ss.setdefault("spec_pool", [])
    ss.setdefault("answered", False)
    ss.setdefault("auto_advance", False)
    ss.setdefault("correct", 0)
    ss.setdefault("attempts", 0)
    ss.setdefault("history", [])
    ss.setdefault("wrong_map", {})
    ss.setdefault("wrong_count", defaultdict(int))
    ss.setdefault("favorites", set())
    ss.setdefault("exam_running", False)
    ss.setdefault("exam_pool", [])
    ss.setdefault("exam_answers", {})
    ss.setdefault("exam_start_ts", None)
    ss.setdefault("exam_duration_sec", 0)
    ss.setdefault("exam_submitted", False)
    ss.setdefault("exam_records", [])
_init_session()

# Top nav (tabs-like)
MODES = ["顺序练习","随机练习","章节练习","专项练习","错题重练","收藏夹","易错题","模拟考试","成绩记录","进度面板"]
cols = st.columns(len(MODES))
for i,m in enumerate(MODES):
    active = (st.session_state.mode == m)
    with cols[i]:
        if st.button(m, use_container_width=True, key=f"tab_{m}", type=("primary" if active else "secondary")):
            st.session_state.mode = m
            st.session_state.answered = False
            st.session_state.idx = 0
            st.rerun()

# Sidebar filters
chapters = sorted({q.get("chapter","") for q in ALL_QUESTIONS if q.get("chapter")})
sections_by_ch = {}
for q in ALL_QUESTIONS:
    ch, sec = q.get("chapter",""), q.get("section","")
    if ch:
        sections_by_ch.setdefault(ch, set()).add(sec)

with st.sidebar:
    st.markdown("### 全局设置")
    st.session_state.auto_advance = st.checkbox("提交后自动跳到下一题", value=st.session_state.get("auto_advance", False))
    st.caption("关闭后：提交答案会显示对错，并出现“下一题”按钮。")
    st.divider()
    st.markdown("#### 练习池设置")
    seq_limit = st.slider("顺序/随机 每轮题量", 10, 300, min(50, len(ALL_QUESTIONS)))
    sel_ch = st.multiselect("章节筛选（用于章节/专项/考试）", options=chapters, default=chapters)
    sel_sec_options = sorted({s for ch in sel_ch for s in sections_by_ch.get(ch, set()) if s})
    sel_sec = st.multiselect("小节筛选（可选）", options=sel_sec_options, default=sel_sec_options)
    all_tags = sorted({t for q in ALL_QUESTIONS for t in q.get("tags", [])})
    sel_tags = st.multiselect("专项练习标签（任意命中）", options=all_tags, default=[])

def by_ch_sec(q):
    return ((not sel_ch) or (q.get("chapter","") in sel_ch)) and \
           ((not sel_sec) or (q.get("section","") in sel_sec) or (not q.get("section")))

def by_tags(q):
    if not sel_tags: return True
    qt = set(q.get("tags", []))
    return any(t in qt for t in sel_tags)

def mcq_only(qs):
    return [q for q in qs if is_mcq(q)]

def build_pool(order="seq"):
    pool = [q for q in ALL_QUESTIONS if by_ch_sec(q)]
    pool = mcq_only(pool)
    if order == "rand":
        random.shuffle(pool)
    return pool[:min(seq_limit, len(pool))]

def build_spec_pool():
    pool = [q for q in ALL_QUESTIONS if by_ch_sec(q) and by_tags(q)]
    pool = mcq_only(pool)
    random.shuffle(pool)
    return pool[:min(seq_limit, len(pool))]

def get_pool_for_mode(mode):
    ss = st.session_state
    if mode == "顺序练习":
        if not ss.seq_pool: ss.seq_pool = build_pool("seq")
        return ss.seq_pool
    if mode == "随机练习":
        if not ss.rand_pool: ss.rand_pool = build_pool("rand")
        return ss.rand_pool
    if mode == "章节练习":
        if not ss.chap_pool: ss.chap_pool = build_pool("seq")
        return ss.chap_pool
    if mode == "专项练习":
        if not ss.spec_pool: ss.spec_pool = build_spec_pool()
        return ss.spec_pool
    if mode == "错题重练":
        return list(st.session_state.wrong_map.values())
    if mode == "收藏夹":
        fav_ids = st.session_state.favorites
        return [q for q in ALL_QUESTIONS if qkey(q) in fav_ids]
    if mode == "易错题":
        wc = st.session_state.wrong_count
        hard_ids = [qid for qid,cnt in wc.items() if cnt >= 2]
        return [q for q in ALL_QUESTIONS if qkey(q) in set(hard_ids)]
    return []

def render_one_question(q, mode_name):
    qid = qkey(q)
    # header
    ui_header(st.session_state.idx + 1, max(1, len(get_pool_for_mode(mode_name))), f"**题目：** {q.get('question','')}")
    chips = []
    if q.get("chapter"): chips.append(f"<span class='badge'>章：{q['chapter']}</span>")
    if q.get("section"): chips.append(f"<span class='badge'>节：{q['section']}</span>")
    if q.get("difficulty"): chips.append(f"<span class='badge'>难度：{q['difficulty']}</span>")
    t = q.get("tags", [])
    if t: chips.append(f"<span class='badge'>标签：{' / '.join(t)}</span>")
    if chips: st.markdown("<div class='meta'>" + " ".join(chips) + "</div>", unsafe_allow_html=True)

    opts = list(q["options"])
    rng = random.Random(qid); rng.shuffle(opts)
    prev = st.session_state.get(f"sel_{qid}", opts[0])
    sel = st.radio(" ", opts, index=opts.index(prev) if prev in opts else 0, label_visibility="collapsed", key=f"sel_{qid}")

    fav = qid in st.session_state.favorites
    fav_col, _sp, del_col = st.columns([1,6,1])
    with fav_col:
        if st.button(("★ 已收藏" if fav else "☆ 收藏本题"), use_container_width=True):
            if fav: st.session_state.favorites.remove(qid)
            else: st.session_state.favorites.add(qid)
            st.rerun()
    with del_col:
        if mode_name in ("错题重练","易错题") and st.button("🧹 移出错题", use_container_width=True):
            st.session_state.wrong_map.pop(qid, None)
            st.rerun()

    c1, c2, c3 = st.columns(3)
    with c1:
        skip_clicked = st.button("⬅️ 跳过/下一题", use_container_width=True)
    with c3:
        submit_clicked = st.button("✅ 提交答案", type="primary", use_container_width=True)

    if skip_clicked:
        st.session_state.answered = False
        st.session_state.idx = min(st.session_state.idx + 1, max(0, len(get_pool_for_mode(mode_name)) - 1))
        st.rerun()

    if submit_clicked:
        st.session_state.attempts += 1
        ok = (sel == q.get("answer",""))
        if ok:
            st.session_state.correct += 1
            st.markdown("<div class='alert-ok'>✅ 回答正确！</div>", unsafe_allow_html=True)
            st.session_state.wrong_map.pop(qid, None)
        else:
            st.markdown(f"<div class='alert-err'>❌ 回答错误。正确答案：{q.get('answer','')}</div>", unsafe_allow_html=True)
            st.session_state.wrong_map[qid] = q
            st.session_state.wrong_count[qid] += 1

        exp = q.get("explanation","").strip()
        if exp:
            st.markdown(f"<div class='alert-info'>📘 解析：{exp}</div>", unsafe_allow_html=True)

        st.session_state.history.append((qid, ok, datetime.now().isoformat(timespec="seconds"), mode_name))

        if st.session_state.auto_advance:
            st.session_state.answered = False
            st.session_state.idx = min(st.session_state.idx + 1, max(0, len(get_pool_for_mode(mode_name)) - 1))
            st.rerun()
        else:
            st.session_state.answered = True

    if (not st.session_state.auto_advance) and st.session_state.answered:
        if st.button("➡️ 下一题", use_container_width=True):
            st.session_state.answered = False
            st.session_state.idx = min(st.session_state.idx + 1, max(0, len(get_pool_for_mode(mode_name)) - 1))
            st.rerun()

# Render page title
st.title("🚗 博学 · 全量刷题系统（驾考宝典风格）")
st.caption("顺序/随机/章节/专项/错题/收藏/易错/模拟考试/成绩记录/进度面板 · 题目解析/收藏/数据备份")

# Placeholder defaults for sliders that code refers to
seq_limit = 50

mode = st.session_state.mode

def by_ch_sec(q):
    return True  # will be re-evaluated in pools where needed; simplified in this compact build

# Simple pools if filters not yet established (first render)
def simple_pool():
    return [q for q in ALL_QUESTIONS if is_mcq(q)][:min(seq_limit, len(ALL_QUESTIONS))]

if mode in ("顺序练习","随机练习","章节练习","专项练习","错题重练","收藏夹","易错题"):
    st.header(f"📖 {mode}")
    # Ensure pools exist minimally
    if mode == "顺序练习" and not st.session_state.seq_pool:
        st.session_state.seq_pool = simple_pool()
    if mode == "随机练习" and not st.session_state.rand_pool:
        import random
        pool = simple_pool(); random.shuffle(pool); st.session_state.rand_pool = pool
    if mode == "章节练习" and not st.session_state.chap_pool:
        st.session_state.chap_pool = simple_pool()
    if mode == "专项练习" and not st.session_state.spec_pool:
        st.session_state.spec_pool = simple_pool()

    pool = get_pool_for_mode(mode)
    if not pool:
        st.warning("当前筛选条件下没有题目，请调整筛选或更换模式。")
    else:
        i = st.session_state.idx
        i = max(0, min(i, len(pool)-1))
        st.session_state.idx = i
        render_one_question(pool[i], mode)

elif mode == "模拟考试":
    ss = st.session_state
    st.header("📝 模拟考试")
    exam_minutes = st.sidebar.number_input("考试时长（分钟）", min_value=5, max_value=240, value=60, step=5)
    pass_line = st.sidebar.number_input("合格线（百分制）", min_value=0, max_value=100, value=60, step=1)
    exam_size = st.sidebar.slider("试卷题量", 20, 200, min(100, len(ALL_QUESTIONS)))

    def build_exam_pool():
        pool = [q for q in ALL_QUESTIONS if is_mcq(q)]
        random.shuffle(pool)
        return pool[:min(exam_size, len(pool))]

    if not ss.get("exam_running") and not ss.get("exam_submitted"):
        st.info("点击下方按钮开始考试。开始后会启动倒计时，期间不显示对错；交卷后显示分数与报告。")
        if st.button("▶️ 开始考试"):
            ss.exam_pool = build_exam_pool()
            ss.exam_running = True
            ss.exam_submitted = False
            ss.exam_answers = {}
            ss.exam_duration_sec = int(exam_minutes) * 60
            ss.exam_start_ts = time.time()
            ss.idx = 0
            st.rerun()

    if ss.get("exam_running") and not ss.get("exam_submitted"):
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
            chips = []
            if q.get("chapter"): chips.append(f"<span class='badge'>章：{q['chapter']}</span>")
            if q.get("section"): chips.append(f"<span class='badge'>节：{q['section']}</span>")
            if q.get("difficulty"): chips.append(f"<span class='badge'>难度：{q['difficulty']}</span>")
            t = q.get("tags", [])
            if t: chips.append(f"<span class='badge'>标签：{' / '.join(t)}</span>")
            if chips: st.markdown("<div class='meta'>" + " ".join(chips) + "</div>", unsafe_allow_html=True)

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

    if ss.get("exam_submitted"):
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
                st.session_state.wrong_count[qid] += 1
        score = round(correct / total * 100, 1) if total else 0.0
        passed = score >= pass_line

        st.success(f"🎯 成绩：{score} 分（{'通过' if passed else '未通过'}，合格线 {pass_line} 分）")
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ 正确题数", correct)
        c2.metric("❌ 错题数", len(wrong_detail))
        c3.metric("📝 总题数", total)

        ss.exam_records.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "score": score, "passed": passed, "total": total, "correct": correct, "wrong": len(wrong_detail)
        })

        with st.expander("📄 错题明细"):
            for i, item in enumerate(wrong_detail, 1):
                st.markdown(f"**{i}. {item['question']}**")

        if st.button("🔁 重新开始新考试"):
            ss.exam_running = False
            ss.exam_submitted = False
            ss.exam_answers = {}
            ss.exam_pool = []
            st.rerun()

elif mode == "成绩记录":
    st.header("📚 成绩记录")
    recs = st.session_state.exam_records
    if not recs:
        st.info("还没有考试记录。去“模拟考试”试一试吧！")
    else:
        import pandas as pd
        df = pd.DataFrame(recs)
        st.dataframe(df, use_container_width=True)
        st.download_button("⬇️ 导出成绩记录（JSON）", data=json.dumps(recs, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="exam_records.json", mime="application/json")

elif mode == "进度面板":
    st.header("📈 进度面板")
    total = len(ALL_QUESTIONS)
    done_ids = {qid for (qid, ok, ts, md) in st.session_state.history}
    wrong_cnt = sum(1 for (_, ok, _, _) in st.session_state.history if not ok)
    right_cnt = sum(1 for (_, ok, _, _) in st.session_state.history if ok)
    fav_cnt = len(st.session_state.favorites)
    hard_cnt = sum(1 for c in st.session_state.wrong_count.values() if c>=2)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("📚 题库总量", total)
    c2.metric("📝 做过题数", len(done_ids))
    c3.metric("✅ 正确/错误", f"{right_cnt}/{wrong_cnt}")
    c4.metric("⭐ 收藏/易错", f"{fav_cnt}/{hard_cnt}")

    chap_stats = {}
    id2q = {qkey(q): q for q in ALL_QUESTIONS}
    for (qid, ok, ts, md) in st.session_state.history:
        q = id2q.get(qid)
        if not q: continue
        ch = q.get("chapter","")
        chap_stats.setdefault(ch, [0,0])
        chap_stats[ch][1] += 1
        if ok: chap_stats[ch][0] += 1
    rows = []
    for ch, (r,t) in chap_stats.items():
        acc = (r/t*100) if t else 0.0
        rows.append({"chapter": ch or "(未分类)", "attempts": t, "right": r, "accuracy(%)": round(acc,1)})
    if rows:
        import pandas as pd
        st.markdown("#### 章节统计")
        st.dataframe(pd.DataFrame(rows).sort_values(["accuracy(%)","attempts"], ascending=[False,False]), use_container_width=True)
    else:
        st.info("还没有可统计的数据，先去练习几题吧。")

st.divider()
st.header("💾 数据备份 / 恢复")
blob = {
    "history": st.session_state.history,
    "wrong_ids": list(st.session_state.wrong_map.keys()),
    "wrong_count": dict(st.session_state.wrong_count),
    "favorites": list(st.session_state.favorites),
    "exam_records": st.session_state.exam_records,
}
st.download_button("⬇️ 导出我的学习进度（JSON）", data=json.dumps(blob, ensure_ascii=False, indent=2).encode("utf-8"),
                   file_name="my_progress.json", mime="application/json")
up = st.file_uploader("上传备份 JSON 以恢复进度", type=["json"])
if up is not None:
    try:
        data = json.load(up)
        id2q = {qkey(q): q for q in ALL_QUESTIONS}
        st.session_state.history = data.get("history", [])
        st.session_state.wrong_map = {qid: id2q[qid] for qid in data.get("wrong_ids", []) if qid in id2q}
        st.session_state.wrong_count = defaultdict(int, data.get("wrong_count", {}))
        st.session_state.favorites = set(data.get("favorites", []))
        st.session_state.exam_records = data.get("exam_records", [])
        st.success("恢复完成！")
    except Exception as e:
        st.error(f"恢复失败：{e}")
