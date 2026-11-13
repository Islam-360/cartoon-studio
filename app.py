import os
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import List
import requests
import streamlit as st
from pydantic import BaseModel
from google import genai
from google.genai import types
import fal_client

# -----------------------------
# إعدادات المجلدات والحفظ المحلي
# -----------------------------
BASE_DIR = Path("studio_workspace")
BASE_DIR.mkdir(exist_ok=True)
CHAR_FILE = BASE_DIR / "characters.json"

st.set_page_config(
    page_title="استوديو يوميات الكرتون الذكي",
    page_icon="🎬",
    layout="wide",
)

# -----------------------------
# نماذج البيانات المهيكلة للـ AI
# -----------------------------
class SceneItem(BaseModel):
    scene_number: int
    speaker: str  # "char1" أو "char2"
    dialogue: str
    emotion_tag: str
    image_prompt: str
    motion_prompt: str

class EpisodePlan(BaseModel):
    episode_title: str
    viral_titles: List[str]
    post_description: str
    hashtags: List[str]
    scenes: List[SceneItem]

# -----------------------------
# دوال مساعدة (FFmpeg & Files)
# -----------------------------
def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def download_file(url: str, dest: Path) -> Path:
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest

def ensure_min_audio_duration(audio_path: Path, min_sec: float = 2.2) -> Path:
    """تمديد الصوت لـ 2.2 ثانية على الأقل لضمان نجاح مزامنة الشفاه."""
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
        ],
        capture_output=True, text=True
    )
    try:
        dur = float(probe.stdout.strip())
    except ValueError:
        dur = min_sec
    if dur >= min_sec:
        return audio_path
    padded_path = audio_path.with_name(f"padded_{audio_path.name}")
    pad_amount = round(min_sec - dur + 0.1, 2)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path), "-af", f"apad=pad_dur={pad_amount}", str(padded_path)],
        check=True, capture_output=True
    )
    return padded_path

def merge_video_and_audio(video_path: Path, audio_path: Path, out_path: Path):
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out_path)
        ],
        check=True, capture_output=True
    )

def concat_episode_clips(clip_paths: List[Path], final_output: Path):
    normalized = []
    for i, clip in enumerate(clip_paths):
        norm = clip.with_name(f"norm_{i}_{clip.name}")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(clip),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(norm)
            ],
            check=True, capture_output=True
        )
        normalized.append(norm)

    list_file = final_output.with_suffix(".txt")
    list_file.write_text("\n".join([f"file '{p.resolve()}'" for p in normalized]), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(final_output)],
        check=True, capture_output=True
    )

def load_characters():
    if CHAR_FILE.exists():
        return json.loads(CHAR_FILE.read_text(encoding="utf-8"))
    return {
        "char1_name": "سعود",
        "char1_desc": "A cheerful 3D Pixar-style cartoon young Arab man in his 20s, wearing a neat white thobe and red-and-white shemagh, expressive big eyes, friendly smile, clean 3D animation render",
        "char1_voice": "Adam",
        "char1_url": "",
        "char2_name": "ماجد",
        "char2_desc": "A funny energetic 3D Pixar-style cartoon young Arab man in his 20s, wearing a bright blue casual hoodie and round glasses, spiky black hair, expressive cartoon face, clean 3D animation render",
        "char2_voice": "Charlie",
        "char2_url": "",
    }

def save_characters(data: dict):
    CHAR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# -----------------------------
# الشريط الجانبي: مفاتيح التشغيل
# -----------------------------
with st.sidebar:
    st.header("🔑 إعدادات المحرك")
    gemini_key = st.text_input("Gemini API Key (من aistudio.google.com)", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    fal_key = st.text_input("fal.ai API Key (من fal.ai)", type="password", value=os.environ.get("FAL_KEY", ""))

    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
    if fal_key:
        os.environ["FAL_KEY"] = fal_key

    st.divider()
    if check_ffmpeg():
        st.success("✅ أداة FFmpeg جاهزة للمونتاج")
    else:
        st.error("⚠️ أداة FFmpeg غير مثبتة. أضف ملف packages.txt وبداخله ffmpeg.")

st.title("🎬 استوديو يوميات الكرتون الخاص")
st.caption("أفكار + اسكربت بلهجات متعددة + ثبات الشخصيات + أصوات + Lip-Sync + تجهيز النشر")

if "chars" not in st.session_state:
    st.session_state["chars"] = load_characters()
if "episode" not in st.session_state:
    st.session_state["episode"] = None
if "scene_assets" not in st.session_state:
    st.session_state["scene_assets"] = {}

tab1, tab2, tab3 = st.tabs([
    "1️⃣ هوية الشخصيتين",
    "2️⃣ المخرج والاسكربت + SEO",
    "3️⃣ الإنتاج والمونتاج النهائي"
])

# ==========================================================
# التبويب 1: تصميم وحفظ الشخصيتين لثباتهما في كل الحلقات
# ==========================================================
with tab1:
    st.subheader("تصميم الصديقين (تُحفظ مرة واحدة لضمان الثبات)")
    chars = st.session_state["chars"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### الشخصية الأولى")
        chars["char1_name"] = st.text_input("اسم الشخصية 1", value=chars["char1_name"])
        chars["char1_voice"] = st.text_input("صوت ElevenLabs المقترح 1", value=chars["char1_voice"])
        chars["char1_desc"] = st.text_area("الوصف البصري الدقيق 1 (بالإنجليزية)", value=chars["char1_desc"], height=120)

        if st.button("🎨 توليد صورة مرجعية للشخصية 1"):
            if not fal_key:
                st.error("أدخل مفتاح FAL_KEY من الشريط الجانبي أولاً.")
            else:
                try:
                    with st.spinner("جاري رسم الشخصية الأولى بدقة عالية..."):
                        res = fal_client.subscribe(
                            "google/nano-banana-2.1",
                            arguments={
                                "prompt": f"Character reference portrait, front view, neutral studio background, {chars['char1_desc']}",
                                "aspect_ratio": "3:4",
                                "resolution": "2K",
                            },
                        )
                        chars["char1_url"] = res["images"][0]["url"]
                        save_characters(chars)
                        st.rerun()
                except Exception as e:
                    st.error(f"حدث خطأ أثناء توليد الصورة: {e}")

        up1 = st.file_uploader("أو ارفع صورة جاهزة للشخصية 1", type=["png", "jpg", "jpeg"], key="up1")
        if up1 and fal_key:
            try:
                tmp1 = BASE_DIR / "char1_upload.png"
                tmp1.write_bytes(up1.read())
                chars["char1_url"] = fal_client.upload_file(str(tmp1))
                save_characters(chars)
                st.success("تم رفع الصورة المرجعية 1")
            except Exception as e:
                st.error(f"تعذر رفع الصورة: {e}")

        if chars["char1_url"]:
            st.image(chars["char1_url"], caption=chars["char1_name"], width=280)

    with col2:
        st.markdown("### الشخصية الثانية")
        chars["char2_name"] = st.text_input("اسم الشخصية 2", value=chars["char2_name"])
        chars["char2_voice"] = st.text_input("صوت ElevenLabs المقترح 2", value=chars["char2_voice"])
        chars["char2_desc"] = st.text_area("الوصف البصري الدقيق 2 (بالإنجليزية)", value=chars["char2_desc"], height=120)

        if st.button("🎨 توليد صورة مرجعية للشخصية 2"):
            if not fal_key:
                st.error("أدخل مفتاح FAL_KEY من الشريط الجانبي أولاً.")
            else:
                try:
                    with st.spinner("جاري رسم الشخصية الثانية بدقة عالية..."):
                        res = fal_client.subscribe(
                            "google/nano-banana-2.1",
                            arguments={
                                "prompt": f"Character reference portrait, front view, neutral studio background, {chars['char2_desc']}",
                                "aspect_ratio": "3:4",
                                "resolution": "2K",
                            },
                        )
                        chars["char2_url"] = res["images"][0]["url"]
                        save_characters(chars)
                        st.rerun()
                except Exception as e:
                    st.error(f"حدث خطأ أثناء توليد الصورة: {e}")

        up2 = st.file_uploader("أو ارفع صورة جاهزة للشخصية 2", type=["png", "jpg", "jpeg"], key="up2")
        if up2 and fal_key:
            try:
                tmp2 = BASE_DIR / "char2_upload.png"
                tmp2.write_bytes(up2.read())
                chars["char2_url"] = fal_client.upload_file(str(tmp2))
                save_characters(chars)
                st.success("تم رفع الصورة المرجعية 2")
            except Exception as e:
                st.error(f"تعذر رفع الصورة: {e}")

        if chars["char2_url"]:
            st.image(chars["char2_url"], caption=chars["char2_name"], width=280)

    if st.button("💾 حفظ بيانات الشخصيتين"):
        save_characters(chars)
        st.success("تم حفظ الشخصيتين بنجاح.")

# ==========================================================
# التبويب 2: المخرج الذكي (أفكار + اسكربت + SEO)
# ==========================================================
with tab2:
    st.subheader("كتابة الحلقة وتجهيزها للانتشار")
    c1, c2, c3 = st.columns(3)
    with c1:
        dialect = st.selectbox("اللغة / اللهجة", [
            "العربية - اللهجة السعودية البيضاء",
            "العربية - اللهجة المصرية الكوميدية",
            "العربية - اللهجة الخليجية",
            "العربية - اللهجة الشامية",
            "العربية الفصحى المبسطة",
            "English (American Casual)",
            "Français",
            "Español",
        ])
    with c2:
        num_scenes = st.slider("عدد المشاهد في الحلقة", min_value=2, max_value=8, value=4)
    with c3:
        tone = st.selectbox("أسلوب الحلقة", ["كوميدي يومي سريع", "موقف محرج ومضحك", "نقاش طريف عن التقنية/الحياة", "نصيحة ساخرة"])

    idea = st.text_area(
        "فكرة الحلقة اليومية (أو اتركه فارغاً ليبتكر الذكاء الاصطناعي فكرة جذابة)",
        placeholder="مثال: ماجد يقنع سعود يفتحون مشروع قهوة مختصة في يوم واحد وتحدث كارثة كوميدية..."
    )

    if st.button("✨ توليد الاسكربت والعناوين (Gemini)", type="primary"):
        if not gemini_key:
            st.error("أدخل Gemini API Key من الشريط الجانبي أولاً.")
        else:
            try:
                with st.spinner("المخرج الذكي يكتب الحوار والمشاهد وعناوين الانتشار..."):
                    client = genai.Client(api_key=gemini_key)
                    chars = st.session_state["chars"]
                    prompt = f"""
أنت مخرج وكاتب محتوى فيروسي لمقاطع الكرتون القصيرة (Reels / Shorts / TikTok).
لديك شخصيتان صديقان:
- char1: {chars['char1_name']} ({chars['char1_desc']})
- char2: {chars['char2_name']} ({chars['char2_desc']})

المطلوب: تأليف حلقة قصيرة مكونة من {num_scenes} مشاهد متسلسلة.
- اللغة/اللهجة المطلوبة للحوار بدقة وتشكيل واضح يساعد النطق الصحيح: {dialect}
- الأسلوب: {tone}
- الفكرة: {idea if idea.strip() else "ابتكر فكرة يومية طريفة ومرتبطة بواقع الشباب وتجذب تفاعل المشاهدين."}

قواعد مهمة:
1. كل جملة حوارية في المشهد تكون قصيرة (بين 5 إلى 14 كلمة) ومكتوبة بلهجة طبيعية مضبوطة بالشكل عند الكلمات الملتبسة.
2. في image_prompt: اكتب باللغة الإنجليزية وصفاً دقيقاً للمشهد 9:16 يذكر بوضوح وجود Image 1 ({chars['char1_name']}) و/أو Image 2 ({chars['char2_name']}) بنفس تصميمهما وملابسهما في خلفية كرتونية ثلاثية الأبعاد متناسقة، ووجههما واضح للكاميرا (مهم جداً لمزامنة الشفاه).
3. في motion_prompt: اكتب بالإنجليزية وصفاً بسيطاً لحركة المتحدث وتعبيرات وجهه.
4. اكتب 5 عناوين جذابة للانتشار، ووصفاً تفاعلياً للمنشور، و10 هاشتاغات قوية.
"""
                    response = client.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=EpisodePlan,
                        ),
                    )
                    plan = EpisodePlan.model_validate_json(response.text)
                    st.session_state["episode"] = plan.model_dump()
                    st.session_state["scene_assets"] = {}
                    st.session_state.pop("current_run_dir", None)
                    st.session_state.pop("final_mp4", None)
                    st.success("تم توليد خطة الحلقة بنجاح! راجع النصوص بالأسفل وعدّل ما تريد.")
            except Exception as e:
                st.error(f"حدث خطأ في توليد الاسكربت: {e}")

    if st.session_state["episode"]:
        ep = st.session_state["episode"]
        st.markdown(f"### 📌 {ep['episode_title']}")
        with st.expander("🚀 حزمة النشر والانتشار (العناوين + الوصف + الهاشتاغات)", expanded=True):
            st.markdown("**عناوين مقترحة:**")
            for t in ep["viral_titles"]:
                st.write(f"- {t}")
            st.text_area("وصف المنشور", value=ep["post_description"], key="seo_desc")
            st.code(" ".join(ep["hashtags"]))

        st.markdown("### 📝 مراجعة وتعديل حوار المشاهد قبل الإنتاج")
        for idx, sc in enumerate(ep["scenes"]):
            with st.container(border=True):
                speaker_name = st.session_state["chars"]["char1_name"] if sc["speaker"] == "char1" else st.session_state["chars"]["char2_name"]
                st.markdown(f"**المشهد {sc['scene_number']} — المتحدث: {speaker_name}**")
                sc["dialogue"] = st.text_input("الحوار (يمكنك تعديل التشكيل واللهجة هنا)", value=sc["dialogue"], key=f"dlg_{idx}")
                sc["image_prompt"] = st.text_area("أمر الصورة (EN)", value=sc["image_prompt"], key=f"imgp_{idx}", height=70)
                sc["motion_prompt"] = st.text_input("أمر الحركة (EN)", value=sc["motion_prompt"], key=f"motp_{idx}")

# ==========================================================
# التبويب 3: الإنتاج (صور + صوت + فيديو + Lip-Sync + مونتاج)
# ==========================================================
with tab3:
    if not st.session_state["episode"]:
        st.info("ولّد اسكربت الحلقة من التبويب الثاني أولاً.")
    else:
        ep = st.session_state["episode"]
        chars = st.session_state["chars"]
        use_lipsync = st.checkbox("تفعيل مزامنة الشفاه (Kling Lip-Sync) لكل مشهد", value=True)

        if "current_run_dir" not in st.session_state:
            run_dir = BASE_DIR / f"episode_{int(time.time())}"
            run_dir.mkdir(parents=True, exist_ok=True)
            st.session_state["current_run_dir"] = str(run_dir)
        ep_dir = Path(st.session_state["current_run_dir"])

        ref_urls = [u for u in [chars.get("char1_url"), chars.get("char2_url")] if u]
        if not ref_urls:
            st.warning("⚠️ لم تحدد صوراً مرجعية للشخصيتين في التبويب الأول؛ قد يقل ثبات الشكل بين المشاهد.")

        for idx, sc in enumerate(ep["scenes"]):
            assets = st.session_state["scene_assets"].setdefault(idx, {})
            speaker_name = chars["char1_name"] if sc["speaker"] == "char1" else chars["char2_name"]
            voice_name = chars["char1_voice"] if sc["speaker"] == "char1" else chars["char2_voice"]

            with st.container(border=True):
                st.markdown(f"#### المشهد {sc['scene_number']}: {speaker_name}")
                st.write(f"💬 _{sc['dialogue']}_")

                c_img, c_aud, c_vid = st.columns(3)

                # 1. الصورة
                with c_img:
                    if st.button("🖼️ توليد صورة المشهد", key=f"gen_img_{idx}"):
                        if not fal_key:
                            st.error("أدخل FAL_KEY أولاً.")
                        else:
                            try:
                                with st.spinner("جاري رسم المشهد..."):
                                    if ref_urls:
                                        res = fal_client.subscribe(
                                            "google/nano-banana-2.1/edit",
                                            arguments={
                                                "prompt": sc["image_prompt"],
                                                "image_urls": ref_urls,
                                                "aspect_ratio": "9:16",
                                                "resolution": "1K",
                                            },
                                        )
                                    else:
                                        res = fal_client.subscribe(
                                            "google/nano-banana-2.1",
                                            arguments={
                                                "prompt": sc["image_prompt"],
                                                "aspect_ratio": "9:16",
                                                "resolution": "1K",
                                            },
                                        )
                                    img_url = res["images"][0]["url"]
                                    local_img = ep_dir / f"scene_{idx}.png"
                                    download_file(img_url, local_img)
                                    assets["image_url"] = img_url
                                    assets["image_path"] = str(local_img)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"خطأ في الصورة: {e}")

                    if assets.get("image_path") and Path(assets["image_path"]).exists():
                        st.image(assets["image_path"], use_container_width=True)

                # 2. الصوت
                with c_aud:
                    if st.button("🎙️ توليد الصوت (AI)", key=f"gen_aud_{idx}"):
                        if not fal_key:
                            st.error("أدخل FAL_KEY أولاً.")
                        else:
                            try:
                                with st.spinner("جاري توليد الصوت..."):
                                    tts_text = f"{sc['emotion_tag']} {sc['dialogue']}"
                                    res = fal_client.subscribe(
                                        "fal-ai/elevenlabs/tts/eleven-v3",
                                        arguments={
                                            "text": tts_text,
                                            "voice": voice_name,
                                            "stability": 0.45,
                                            "similarity_boost": 0.75,
                                        },
                                    )
                                    aud_url = res["audio"]["url"]
                                    local_aud = ep_dir / f"scene_{idx}.mp3"
                                    download_file(aud_url, local_aud)
                                    padded = ensure_min_audio_duration(local_aud, 2.2)
                                    if padded != local_aud:
                                        aud_url = fal_client.upload_file(str(padded))
                                        local_aud = padded
                  
