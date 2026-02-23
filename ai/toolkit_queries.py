"""
Toolkit Analysis Queries — 10 deep consumer research prompts
=============================================================
Adapted from NotebookLM/social_comment_analysis_toolkit.md for
automated execution via the NotebookLM bridge.

Execution order follows the toolkit's recommended progressive
context build (each query can reference previous answers via
NLM session continuity).
"""


def get_toolkit_queries(
    topic: str,
    comment_count: int,
    platforms: list[str],
) -> list[dict]:
    """Build the ordered list of 10 toolkit queries.

    Returns list of dicts with 'id' and 'question' keys,
    compatible with NotebookLMBridge.create_and_query().
    """
    platforms_str = ", ".join(p.title() for p in platforms)
    ctx = (
        f"จากข้อมูล comment ทั้งหมดเกี่ยวกับ \"{topic}\" "
        f"จาก {platforms_str} ({comment_count} comments) "
        f"ที่ upload ไว้ในเอกสาร:"
    )

    queries = [
        # 1. Emotion & Intent Deep Dive (Prompt 1)
        {
            "id": "emotion_intent",
            "question": f"""{ctx}

คุณคือ Consumer Psychologist ที่เชี่ยวชาญการวิเคราะห์พฤติกรรมผู้บริโภคจาก social media

ให้วิเคราะห์ comment ทั้งหมดดังนี้:

## 1. Emotion Classification
จัดกลุ่ม emotion ที่ลึกกว่า positive/negative โดยใช้ emotion เหล่านี้:
- Craving/Desire (อยากได้, อยากลอง)
- Satisfaction/Delight (พอใจ, ประทับใจ)
- Frustration/Disappointment (ผิดหวัง, หงุดหงิด)
- FOMO (กลัวพลาด, อิจฉา)
- Nostalgia (คิดถึง, นึกถึงความหลัง)
- Curiosity (สงสัย, อยากรู้)
- Guilt/Conflict (รู้สึกผิด, ลังเล)
- Trust/Loyalty (เชื่อมั่น, ภักดี)
- Surprise (ประหลาดใจ ทั้งในทางดีและไม่ดี)
- Social Belonging (อยากเป็นส่วนหนึ่ง, tag เพื่อน)

หาก comment มีหลาย emotion ให้ระบุทั้งหมด โดยเรียง primary emotion ก่อน

## 2. Intent Detection
วิเคราะห์ว่า comment แต่ละอันมี intent อะไรซ่อนอยู่:
- Purchase Intent, Consideration, Advocacy, Information Seeking
- Complaint/Feedback, Social Sharing, Barrier Expression
- Re-purchase Signal, Churn Signal

## 3. "Why Behind the Why"
สำหรับ comment ที่น่าสนใจที่สุด ให้วิเคราะห์:
- สิ่งที่ลูกค้า "พูด" (Surface Message)
- สิ่งที่ลูกค้า "หมายถึงจริงๆ" (Underlying Meaning)
- สิ่งที่ลูกค้า "ต้องการ" (Unspoken Need)

## Output Format
1. ตาราง comment ตัวอย่างพร้อม emotion, intent, surface/underlying/unspoken
2. Top 5 Emotions ที่พบบ่อยที่สุด พร้อมสัดส่วน %
3. Top 5 Intents ที่พบบ่อยที่สุด พร้อมสัดส่วน %
4. Key Insights 3-5 ข้อที่น่าสนใจที่สุด""",
        },

        # 2. Tension Mapping (Prompt 2)
        {
            "id": "tension_mapping",
            "question": f"""{ctx}

คุณคือ Innovation Strategist ที่เชี่ยวชาญในการค้นหาโอกาสทางธุรกิจจากเสียงของลูกค้า

ให้ค้นหา "Tension" หรือ "ความขัดแย้งภายใน" ที่ซ่อนอยู่ใน comment โดย tension คือเมื่อลูกค้าต้องการ 2 สิ่งที่ขัดแย้งกัน

## ประเภท Tension ที่ต้องมองหา:
1. Value vs. Budget
2. Desire vs. Guilt
3. Convenience vs. Quality
4. Awareness vs. Accessibility
5. Loyalty vs. Curiosity
6. Personal vs. Social
7. Expectation vs. Reality
8. Time vs. Desire
9. Health vs. Indulgence
10. Trust vs. Risk

## วิธีวิเคราะห์:
### ขั้นที่ 1: Tension Detection — สแกนทุก comment แล้วจัดกลุ่ม
### ขั้นที่ 2: Tension Ranking — เรียงลำดับจากมากไปน้อย
### ขั้นที่ 3: Innovation Opportunity — สำหรับ Top 5 Tensions ให้เสนอ:
- Tension, ตัวอย่าง Comment, Customer Conflict
- Innovation Opportunity (อย่างน้อย 2 ไอเดีย)
- Quick Win (ทำได้ใน 1 สัปดาห์)
- Big Bet (ลงทุนสร้าง impact ใหญ่)

## Output Format
ส่วนที่ 1: Tension Heatmap (ตาราง | Tension Type | จำนวน | % | ระดับความสำคัญ)
ส่วนที่ 2: Top 5 Tension Deep Dive
ส่วนที่ 3: Strategic Summary""",
        },

        # 3. Unspoken Needs (Prompt 9)
        {
            "id": "unspoken_needs",
            "question": f"""{ctx}

คุณคือ Consumer Insight Specialist ที่เชี่ยวชาญการอ่าน "ระหว่างบรรทัด"

ภารกิจ: ค้นหาสิ่งที่ลูกค้า "ต้องการพูดแต่ไม่ได้พูด" จาก comment

## Framework: 3 Layers of Meaning
สำหรับทุก comment ที่มี signal ของ unspoken need ให้วิเคราะห์:
| Layer | คำอธิบาย |
|-------|----------|
| Said (พูด) | สิ่งที่ comment บอกตรงๆ |
| Meant (หมายถึง) | สิ่งที่ตั้งใจจะสื่อจริงๆ |
| Need (ต้องการ) | ความต้องการลึกๆ ที่ซ่อนอยู่ |

## ประเภท Unspoken Need:
1. Feature Request ที่ซ่อน
2. Barrier ที่ไม่กล้าพูดตรง
3. Comparison ที่ imply
4. Social Proof Seeking
5. Customization Need
6. Occasion Gap
7. Emotional Need
8. Belonging Need

## Output:
### ส่วนที่ 1: Unspoken Need Table
| Comment | Said | Meant | Need | Need Category | Business Opportunity |

### ส่วนที่ 2: Need Priority Matrix (Frequency × Intensity × Actionability)

### ส่วนที่ 3: "Jobs to Be Done" Summary
5-8 JTBD statements: "เมื่อฉัน [สถานการณ์] ฉันต้องการ [need] เพื่อที่จะ [ผลลัพธ์]" """,
        },

        # 4. Tribal Language (Prompt 8)
        {
            "id": "tribal_language",
            "question": f"""{ctx}

คุณคือ Sociolinguist ที่เชี่ยวชาญการวิเคราะห์ภาษาเพื่อเข้าใจกลุ่มสังคม

ให้วิเคราะห์ "ภาษา" ที่ลูกค้าใช้เป็นเครื่องมือในการจัด segment

## ขั้นที่ 1: Linguistic Feature Extraction
- คำที่ใช้บ่อย, Slang & Jargon, Emoji Pattern
- Sentence Structure, Tone, Code-switching
- Superlatives, Formality Level

## ขั้นที่ 2: Tribe Identification (4-6 กลุ่ม)
สำหรับแต่ละ Tribe:
- ชื่อ Tribe (เช่น "The Hype Tribe", "The Critic Circle")
- Signature Language, Communication Style
- Inferred Values, Inferred Identity
- Social Influence, ตัวอย่าง Comment 5 ข้อ

## ขั้นที่ 3: Tribe Dynamics
- Tribe ที่มี influence สูงสุด, Early Adopter vs. Late Majority
- Shared language vs. Divisive language

## ขั้นที่ 4: Communication Playbook
สำหรับแต่ละ Tribe:
- Tone of Voice, คำ/วลีที่ควรใช้, คำ/วลีที่ห้ามใช้
- Content Format ที่จะ engage มากที่สุด
- ตัวอย่าง Caption ที่ออกแบบเฉพาะ""",
        },

        # 5. Comment-Born Persona (Prompt 3)
        {
            "id": "comment_persona",
            "question": f"""{ctx}

คุณคือ Qualitative Researcher ที่เชี่ยวชาญการสร้าง Customer Persona จากข้อมูลจริง

ภารกิจ: สร้าง Customer Persona จาก comment จริงๆ (Comment-Born Persona)

## ขั้นที่ 1: Behavioral Clustering
จัดกลุ่ม comment ตาม behavioral pattern (ภาษา, สิ่งที่พูดถึง, พฤติกรรม, platform) → 4-6 กลุ่ม

## ขั้นที่ 2: Persona Building
สำหรับแต่ละกลุ่ม สร้าง Persona Card:
- ชื่อ Persona (เช่น "Night Craver", "Social Foodie", "Deal Hunter")
- Persona Archetype (สรุป 1 ประโยค)
- Defining Behavior, Language Style, Primary Platform
- Key Emotions, Key Tensions, Motivations, Barriers
- Representative Quotes (3-5 comment จริง)
- จำนวนและสัดส่วน

## ขั้นที่ 3: Persona Relationship Map
- กลุ่มไหน influence กลุ่มไหน?
- โอกาสเปลี่ยนกลุ่ม? Lifetime value สูงสุด?

## ขั้นที่ 4: Strategic Recommendations
สำหรับแต่ละ persona: สื่อสารอย่างไร, ผ่าน platform ไหน, message อะไร, opportunity ที่ยังไม่ได้ tap""",
        },

        # 6. Reverse Day-in-Life (Prompt 4)
        {
            "id": "reverse_day_in_life",
            "question": f"""{ctx}

คุณคือ Ethnographic Researcher ที่เชี่ยวชาญการทำความเข้าใจชีวิตประจำวันของผู้บริโภค

ภารกิจ: ใช้เบาะแส (clues) จาก comment เพื่อ reconstruct "Day-in-Life" ของลูกค้าแต่ละกลุ่ม

## Signal ที่ต้องมองหา:
1. Time Signals — เวลาที่ comment หรือคำบอกเวลา
2. Context Signals — "สั่งให้ลูก", "กินกับแฟน", "เลี้ยงทีม"
3. Location Signals — "delivery ส่งถึงคอนโด", "สั่งไปออฟฟิศ"
4. Platform Signals — platform บอก media behavior
5. Language Signals — ภาษาบอก demographic
6. Behavioral Signals — tag เพื่อน, comment ยาว, emoji เยอะ

## ขั้นตอน:
### ขั้นที่ 1: Signal Extraction — ดึง signal ทั้ง 6 ประเภท
### ขั้นที่ 2: Pattern Assembly — จัดกลุ่มคนที่ signal คล้ายกัน
### ขั้นที่ 3: Day-in-Life Construction (3-5 กลุ่ม)
- ชื่อกลุ่ม (เช่น "The Busy Parent", "The Night Owl Student")
- วันธรรมดา: เช้า/สาย-เที่ยง/บ่าย/เย็น-ค่ำ
- วันหยุด: ชีวิตเปลี่ยนอย่างไร
- Key Moments of Truth — จุดตัดสินใจ
- หลักฐานจาก Comment จริง

### ขั้นที่ 4: Segment Discovery
- segment ใหม่ที่ไม่เคยคิดมาก่อน? gap ที่แบรนด์เติมได้? Moment of Truth สำคัญที่สุด?""",
        },

        # 7. Persona Interview (Prompt 5 — converted to non-interactive)
        {
            "id": "persona_interview",
            "question": f"""{ctx}

จาก Persona ที่สร้างขึ้นในการวิเคราะห์ก่อนหน้านี้ (Comment-Born Persona) ให้สร้าง Persona Profile Cards แบบละเอียดสำหรับแต่ละ persona

สำหรับแต่ละ Persona ให้สร้างข้อมูลดังนี้:

## Persona Profile Card

### 1. แนะนำตัว
เขียนคำแนะนำตัวสั้นๆ ในฐานะลูกค้าคนนี้ (เป็นธรรมชาติ ไม่ formal) ใช้ภาษาตาม Language Style ของ persona

### 2. Sample Interview Q&A (5 คำถาม)
จำลองการสัมภาษณ์ โดยถามคำถามเชิงลึกเกี่ยวกับ:
- พฤติกรรมการใช้งาน/ซื้อสินค้า
- แรงจูงใจและอุปสรรค
- ประสบการณ์กับแบรนด์/สินค้า
- สิ่งที่อยากให้เปลี่ยนแปลง
- อะไรที่ทำให้ตัดสินใจซื้อ/ไม่ซื้อ

ให้คำตอบเป็นธรรมชาติ สั้นกระชับ 1-3 ประโยค เหมือนคุยกับคนจริง มี emotion ตามธรรมชาติของ persona

### 3. Key Quotes
3-5 คำพูดที่เป็นตัวแทนของ persona นี้ (จาก comment จริง)

### 4. Strategic Notes
- Insight สำคัญที่ได้จาก persona นี้
- โอกาสทางธุรกิจ
- ข้อควรระวังในการสื่อสาร""",
        },

        # 8. Cross-Platform Identity (Prompt 6)
        {
            "id": "cross_platform",
            "question": f"""{ctx}

คุณคือ Digital Anthropologist ที่เชี่ยวชาญพฤติกรรมผู้ใช้ข้าม platform

ให้วิเคราะห์ความแตกต่างของพฤติกรรม comment ในแต่ละ platform

## ขั้นที่ 1: Platform Culture Analysis
ตาราง:
| มิติ | {' | '.join(p.title() for p in platforms)} |
ครอบคลุม: ความยาว comment เฉลี่ย, โทนภาษาหลัก, Emoji usage, Topic ที่พูดถึงบ่อย, Emotion ที่พบมาก, Intent ที่พบมาก, ระดับ engagement

## ขั้นที่ 2: Platform-Specific Persona
คน "ประเภทเดียวกัน" แสดงออกต่างกันอย่างไรในแต่ละ platform

## ขั้นที่ 3: Content Strategy Implications
1. แต่ละ platform ควร post content แบบไหน
2. ภาษาและโทนที่ควรใช้
3. ช่วงเวลาที่ดีที่สุดในการ post
4. topic ที่ควรพูดและไม่ควรพูด

## ขั้นที่ 4: Hidden Opportunity
insight ที่เห็นได้จากการมอง "ข้าม platform" ที่มองจาก platform เดียวจะไม่เห็น""",
        },

        # 9. Comment Journey Mapping (Prompt 7)
        {
            "id": "comment_journey",
            "question": f"""{ctx}

คุณคือ Customer Journey Analyst

ให้วิเคราะห์ "การเดินทาง" ของลูกค้าจาก comment pattern

## ขั้นที่ 1: Repeat Commenter Detection
ค้นหา username ที่ comment มากกว่า 1 ครั้ง แล้วเรียงตาม timeline
| Username | ครั้งที่ | Platform | Comment | Stage |

## ขั้นที่ 2: Journey Stage Classification
- Discovery, Interest, Trial, Evaluation
- Loyalty, Advocacy, Churn Risk, Win-back

## ขั้นที่ 3: Journey Pattern Analysis
- Happy Path: Discovery → Interest → Trial → Loyalty → Advocacy
- Drop-off Path: Interest → Trial → หายไป
- Bounce-back Path: Loyalty → Churn Risk → Win-back
- Fast Track: Discovery → Trial → Loyalty
ระบุจำนวนคนในแต่ละ pattern

## ขั้นที่ 4: Critical Moments
- ช่วง transition ที่ลูกค้า "หลุด" มากที่สุด?
- Trigger ที่ทำให้เปลี่ยน stage?

## ขั้นที่ 5: Intervention Recommendations
สำหรับแต่ละ drop-off point: ป้องกัน, ดึงกลับ, เร่ง stage""",
        },

        # 10. Full Synthesis (Prompt 10)
        {
            "id": "full_synthesis",
            "question": f"""{ctx}

คุณคือ Chief Strategy Officer ที่ต้องนำเสนอ Customer Insight Report ต่อ CEO

จากผลการวิเคราะห์ก่อนหน้านี้ทั้ง 9 การวิเคราะห์ (Emotion & Intent, Tension Mapping, Unspoken Needs, Tribal Language, Comment-Born Personas, Day-in-Life, Persona Interview, Cross-Platform, Comment Journey) ให้สังเคราะห์ทุกอย่างเป็น Strategic Report:

## ส่วนที่ 1: Executive Summary (สรุป 3 insight สำคัญที่สุด)

## ส่วนที่ 2: Customer Truth
- ลูกค้าเป็นใครจริงๆ? (จาก persona + tribe)
- ชีวิตเป็นอย่างไร? (จาก day-in-life)
- ต้องการอะไรที่ยังไม่ได้รับ? (จาก unspoken needs + JTBD)

## ส่วนที่ 3: Opportunity Map (Impact vs. Effort)
- Quick Wins (Impact สูง, Effort ต่ำ)
- Strategic Bets (Impact สูง, Effort สูง)
- Low-hanging Fruit (Impact ต่ำ, Effort ต่ำ)
- Deprioritize (Impact ต่ำ, Effort สูง)

## ส่วนที่ 4: Action Plan (Top 5 Opportunities)
What, Why (อ้างอิง data), Who, When, How to Measure (KPI)

## ส่วนที่ 5: Communication Playbook
- Message สำหรับแต่ละ persona/tribe
- Platform strategy
- Content calendar recommendations

## ส่วนที่ 6: What We Still Don't Know
- คำถามที่ data ยังตอบไม่ได้
- Research ที่ควรทำต่อ
- ข้อจำกัดของการวิเคราะห์""",
        },
    ]

    return queries


# Tab display configuration: query_id → tab label
TOOLKIT_TAB_CONFIG = [
    ("full_synthesis", "Strategic Synthesis"),
    ("emotion_intent", "Emotions & Intent"),
    ("tension_mapping", "Tensions & Opportunities"),
    ("unspoken_needs", "Unspoken Needs"),
    ("tribal_language", "Tribal Language"),
    ("comment_persona", "Customer Personas"),
    ("reverse_day_in_life", "Day-in-Life"),
    ("persona_interview", "Persona Profiles"),
    ("cross_platform", "Cross-Platform"),
    ("comment_journey", "Customer Journey"),
]


def get_toolkit_query_count() -> int:
    """Return the fixed number of toolkit queries (always 10)."""
    return 10
