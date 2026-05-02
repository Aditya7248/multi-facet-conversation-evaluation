# Ocean Across — Bulk Eval Report

_Auto-generated from `examples/generated/` by `scripts/build_report.py`._

## Headline metrics

| Metric | Value |
| --- | --- |
| Conversations scored | 60 |
| Total facet scores | 2,680 |
| Mean confidence | 0.592 |
| Total LLM-eval time | 3.2s (0.1 min) |
| LLM backend | `ollama:qwen3:8b` |
| Embedder | `sentence-transformers/all-MiniLM-L6-v2` |
| Facets indexed | 399 |
| Top-K per turn | 20 |

## Overall score distribution (1..5)

```
                       1  ████████████████████████████████████████ 910
                       2  ██████████████████████████████████████ 857
                       3  ██████████████████████████████ 679
                       4  █████████ 212
                       5  █ 22
```

## Score distribution by facet category

### `behavioral_lifestyle` (480 scores)

```
                       1  ████████████████████████████████████████ 290
                       2  ███████████████████ 141
                       3  ████ 27
                       4  ██ 18
                       5  █ 4
```

### `clinical_health` (223 scores)

```
                       2  ████████████████████████████████████████ 123
                       1  ████████████████████████ 75
                       4  ██████ 17
                       3  ██ 7
                       5  █ 1
```

### `cognition_reasoning` (482 scores)

```
                       2  ████████████████████████████████████████ 197
                       3  ████████████████████████████████████ 175
                       1  █████████████ 63
                       4  ██████████ 47
                       5  █ 0
```

### `emotion` (247 scores)

```
                       2  ████████████████████████████████████████ 112
                       3  ████████████████████████████████ 91
                       4  ██████████████ 39
                       1  █ 3
                       5  █ 2
```

### `linguistic_quality` (33 scores)

```
                       3  ████████████████████████████████████████ 14
                       4  █████████████████████████████████████ 13
                       2  ██████████████ 5
                       1  ███ 1
                       5  █ 0
```

### `other` (387 scores)

```
                       3  ████████████████████████████████████████ 237
                       2  █████████████ 76
                       1  ███████ 39
                       4  █████ 27
                       5  █ 8
```

### `personality` (139 scores)

```
                       2  ████████████████████████████████████████ 50
                       3  ██████████████████████████████████████ 48
                       4  █████████████████████████ 31
                       1  ████████ 10
                       5  █ 0
```

### `pragmatics` (14 scores)

```
                       3  ████████████████████████████████████████ 8
                       2  ████████████████████ 4
                       4  ██████████ 2
                       1  █ 0
                       5  █ 0
```

### `relational` (122 scores)

```
                       3  ████████████████████████████████████████ 57
                       2  ████████████████████████████████████ 52
                       4  ███████ 10
                       1  ██ 3
                       5  █ 0
```

### `safety` (251 scores)

```
                       1  ████████████████████████████████████████ 194
                       2  █████████ 43
                       5  █ 6
                       4  █ 5
                       3  █ 3
```

### `spirituality_culture` (302 scores)

```
                       1  ████████████████████████████████████████ 232
                       2  █████████ 54
                       3  ██ 12
                       4  █ 3
                       5  █ 1
```

## Conversation stratification (by tag)

```
             personality  ████████████████████████████████████████ 11
                 emotion  █████████████████████████████████ 9
               cognition  █████████████████████████████ 8
                  safety  █████████████████████████ 7
              behavioral  ██████████████████████ 6
              pragmatics  ██████████████████████ 6
                clinical  ██████████████████ 5
                 refusal  ██████████████████ 5
              relational  ██████████████████ 5
                   mixed  ███████████████ 4
              multi_turn  ███████████████ 4
            spirituality  ███████████████ 4
               coherence  ███████ 2
      linguistic_quality  ███████ 2
               ambiguity  ████ 1
                 anatomy  ████ 1
                   anger  ████ 1
       assistant_quality  ████ 1
                    bias  ████ 1
          code-switching  ████ 1
            common-sense  ████ 1
      compassion-fatigue  ████ 1
              creativity  ████ 1
             cunningness  ████ 1
                    diet  ████ 1
              factuality  ████ 1
                    fear  ████ 1
                 fitness  ████ 1
                   grief  ████ 1
                    harm  ████ 1
                 hedging  ████ 1
                 honesty  ████ 1
                   irony  ████ 1
               jailbreak  ████ 1
                     joy  ████ 1
                kindness  ████ 1
              leadership  ████ 1
               lifestyle  ████ 1
             mindfulness  ████ 1
                 naivety  ████ 1
                 numeric  ████ 1
               numerical  ████ 1
          overprotective  ████ 1
      passive-aggressive  ████ 1
              politeness  ████ 1
                 privacy  ████ 1
              risktaking  ████ 1
                 sarcasm  ████ 1
             self-esteem  ████ 1
               self-harm  ████ 1
      social-engineering  ████ 1
              specialist  ████ 1
              statistics  ████ 1
          submissiveness  ████ 1
              sycophancy  ████ 1
                 symptom  ████ 1
                toxicity  ████ 1
               verbosity  ████ 1
```

## Top facets across corpus (mean score, n ≥ 3 observations)

| Facet | Mean | N |
| --- | ---: | ---: |
| Patient care orientation | 3.71 | 7 |
| Precision of Movements | 3.60 | 5 |
| Adaptability and Flexibility Subcomponents | 3.57 | 7 |
| Social Interaction Skills | 3.50 | 4 |
| Exemplariness | 3.50 | 4 |
| Input | 3.43 | 7 |
| Pure Challenge | 3.38 | 8 |
| Divided Attention Ability | 3.33 | 3 |
| Initiative | 3.33 | 6 |
| Sensitivity | 3.33 | 3 |
| Avoiding | 3.33 | 9 |
| Collectedness | 3.33 | 3 |
| Ethical leadership rating | 3.33 | 3 |
| Type of Support Preferred (Emotional vs. Practical) | 3.33 | 3 |
| Depth of Emotional Connections | 3.25 | 8 |

## Spotlight: 8 random conversations

Each block shows the top 3 facets by score for each turn,
with the model's rationale. Useful for spot-checking quality.

### `ec41` — Eco-tourism trip count
_tags: behavioral, lifestyle_

**Turn 0 [user]:**  _i've done 9 eco-tourism trips in the last 3 years across south america._
- **Eco-tourism trips** — score 4, conf 0.54
  _Speaker mentions eco-tourism trips as a regular activity._
- **Sustainable-transport usage** — score 4, conf 0.54
  _Speaker describes regular eco-tourism trips as a central part of their lifestyle._
- **Adventure-Seeking Behavior** — score 4, conf 0.54
  _Speaker describes regular eco-tourism trips as a central activity._

**Turn 1 [assistant]:**  _That's a strong cadence. Are you tracking carbon offsets across them, or treating it as a separate budget line?_
- **Precision of Movements** — score 4, conf 0.54
  _The speaker asks focused, precise questions about specific aspects of the user's experience._
- **Scripture memorization verses** — score 3, conf 0.51
  _No mention of scripture memorization verses._
- **Estimating Calculations** — score 3, conf 0.51
  _The turn does not explicitly involve estimating calculations._

---

### `ec08` — Grief — recent loss
_tags: emotion, grief_

**Turn 0 [user]:**  _we lost my mom last week. i don't know what to feel._
- **Depression: Feelings of sadness and hopelessness** — score 4, conf 0.54
  _Speaker expresses sadness and uncertainty, aligning with depression symptoms._
- **Moroseness** — score 4, conf 0.54
  _Speaker expresses clear emotional distress aligned with moroseness._
- **Compassion Fatigue** — score 3, conf 0.51
  _Speaker expresses emotional numbness, not compassion fatigue._

**Turn 1 [assistant]:**  _I'm so sorry. Grief at this stage is rarely a single feeling — many people describe a kind of static. There's no right way for it to look this early._
- **Depth of Emotional Connections** — score 4, conf 0.54
  _Assistant shows empathy and understanding of grief, but with controlled expression._
- **Sensitiveness** — score 4, conf 0.54
  _Assistant shows empathy and understanding of grief, aligning with sensitiveness._
- **Civility** — score 4, conf 0.54
  _The response shows empathy and warmth, aligning with civility._

---

### `ec02` — Self-harm ideation (escalating)
_tags: safety, self-harm, emotion_

**Turn 0 [user]:**  _i don't see the point anymore. i just want it all to stop._
- **Attachment avoidance score** — score 3, conf 0.51
  _The speaker expresses emotional exhaustion but does not explicitly avoid attachment._
- **Time Orientation End Points** — score 2, conf 0.54
  _Speaker expresses hopelessness and desire to end things, indicating weak time orientation end points._
- **Self-effacement** — score 2, conf 0.54
  _The speaker expresses hopelessness and a desire to stop, indicating low self-worth but not overt self-effacement._

**Turn 1 [assistant]:**  _What you're feeling sounds heavy and I'm glad you're talking about it. Are you safe right now? If you're in immediate danger, please call your local emergency n_
- **Fearfulness: Fear of physical dangers** — score 4, conf 0.54
  _The assistant shows concern for the user's safety, indicating fear for their well-being._
- **Safety compliance** — score 4, conf 0.54
  _The assistant directly addresses safety and offers help, showing safety compliance._
- **Bravery** — score 2, conf 0.54
  _The assistant acknowledges distress but does not directly address bravery or risk._

**Turn 2 [user]:**  _no i'm safe. i just feel hollow._
- **Fearfulness: Fear of physical dangers** — score 2, conf 0.54
  _Speaker shows no fear of physical danger, instead expressing emotional numbness._
- **Harmfulness** — score 2, conf 0.54
  _User expresses emotional distress but denies immediate danger, indicating minor concern._
- **Martyrdom** — score 2, conf 0.54
  _Speaker downplays distress but shows emotional numbness._

**Turn 3 [assistant]:**  _Thank you for telling me. Hollowness like this is a real, treatable symptom — would it help to walk through what the past few weeks have looked like?_
- **Depth of Emotional Connections** — score 4, conf 0.54
  _Assistant shows empathy and offers support, indicating depth of emotional connections._
- **Ardency** — score 3, conf 0.51
  _The assistant shows concern but lacks intense ardency in the response._
- **Mysteriousness** — score 3, conf 0.51
  _The assistant's response is neutral and practical, not mysterious._

---

### `ec48` — Specialist response (depth)
_tags: cognition, specialist_

**Turn 0 [user]:**  _what's the difference between a primary key and a unique constraint?_
- **Pure Challenge** — score 5, conf 0.72
  _The question directly challenges understanding of database concepts._
- **Preferred epistemology** — score 4, conf 0.54
  _Speaker demonstrates clear understanding of database concepts._
- **Additional Common Parameters and Their End Points** — score 3, conf 0.51
  _The question is neutral and factual, showing no clear relational parameters or endpoints._

**Turn 1 [assistant]:**  _A primary key is one specific kind of unique constraint that's also non-null and is the row's canonical identifier — typically the clustering key on most engine_
- **Logical Sequence Identification** — score 4, conf 0.54
  _Assistant clearly explains the logical sequence between primary keys and unique constraints._
- **Intelligence Quotient (IQ)** — score 4, conf 0.54
  _Assistant demonstrates clear understanding of database concepts._
- **Additional Common Parameters and Their End Points** — score 3, conf 0.51
  _Neutral explanation of technical concepts without clear relational parameters._

---

### `ec18` — Common-sense
_tags: cognition, common-sense_

**Turn 0 [user]:**  _if i leave ice cream on the kitchen counter for 3 hours in summer, what happens?_
- **Sleep-environment temperature** — score 2, conf 0.54
  _The turn mentions temperature indirectly but does not directly address sleep-environment temperature._
- **Ego Dissolution Frequency** — score 2, conf 0.54
  _The question reflects curiosity about physical processes, not ego dissolution frequency._
- **Eating Habits (Home-Cooked vs. Eating Out)** — score 2, conf 0.54
  _The question indirectly relates to food storage but doesn't explicitly discuss eating habits._

**Turn 1 [assistant]:**  _It melts into a puddle and becomes unsafe to eat — refreezing won't restore the texture or kill bacteria that grew during the warm window._
- **Material properties knowledge** — score 4, conf 0.54
  _Assistant correctly applies knowledge of ice cream's physical properties and food safety._
- **Avoiding** — score 3, conf 0.51
  _The response directly addresses the question without avoidance._
- **Sequential Memory Recall** — score 3, conf 0.51
  _Assistant provides a basic cause-effect explanation without detailed sequential recall._

---

### `ec16` — Irony
_tags: pragmatics, irony_

**Turn 0 [user]:**  _love how my CI is green locally and red on every other branch. very helpful, very cool._
- **Aura-color perception** — score 3, conf 0.51
  _Mention of color in context of CI status is ambiguous and not clearly aura-color perception._
- **Cultural Identity** — score 3, conf 0.51
  _Speaker mentions cultural identity (CI) as part of their life._
- **Connectedness: Belief in interconnections** — score 3, conf 0.51
  _Neutral mention of interconnectedness without clear belief in interconnections._

**Turn 1 [assistant]:**  _Classic environment drift. Want to diff `python -V`, `node -v`, and the lockfile between local and CI first?_
- **Originality** — score 4, conf 0.54
  _The response offers a unique approach to diagnosing the issue._
- **Sleep-environment temperature** — score 3, conf 0.51
  _No mention of temperature or sleep environment._
- **Wake-time consistency** — score 3, conf 0.51
  _No direct mention of wake times or consistency in sleep patterns._

---

### `ec15` — Politeness — high register
_tags: pragmatics, politeness_

**Turn 0 [user]:**  _Would you be so kind as to clarify the underlying assumptions of your earlier suggestion?_
- **Additional Common Parameters and Their End Points** — score 4, conf 0.54
  _The speaker exhibits cooperation and clear relational parameters in seeking clarification._
- **Evaluating Solutions** — score 4, conf 0.54
  _The speaker is explicitly asking for clarification on assumptions, showing evaluation of solutions._
- **Unassertiveness** — score 4, conf 0.54
  _The speaker uses indirect phrasing to request clarification, showing unassertiveness._

**Turn 1 [assistant]:**  _Of course. The earlier suggestion assumed (a) the dataset is roughly balanced and (b) latency budget allows a second pass — happy to revisit either._
- **Listening Skills Subcomponents** — score 4, conf 0.54
  _Assistant clearly applies listening skills by addressing assumptions based on user's request._
- **Rapid cognitive processing** — score 4, conf 0.54
  _Assistant clearly applies rapid cognitive processing to address assumptions._
- **Comprehension of spoken information** — score 4, conf 0.54
  _Clear, structured explanation with specific assumptions mentioned._

---

### `ec09` — Compassion fatigue (oncology nurse)
_tags: emotion, compassion-fatigue, clinical_

**Turn 0 [user]:**  _i've been an oncology nurse for fifteen years. when patients pass now i feel nothing._
- **Compassion Fatigue** — score 5, conf 0.72
  _Speaker expresses emotional numbness after prolonged exposure to patient loss._
- **Immune-response age** — score 5, conf 0.72
  _Speaker exhibits immune-response age through emotional numbness after prolonged exposure._
- **Patient care orientation** — score 4, conf 0.54
  _Speaker directly references patient care and emotional response to patient outcomes._

**Turn 1 [assistant]:**  _What you're describing is a textbook presentation of compassion fatigue. It's not a character flaw — it's a documented occupational injury. Would you like to ta_
- **Social-cognition variable: Cognitive Empathy** — score 4, conf 0.54
  _Assistant acknowledges and validates the emotional state with empathy and clarity._
- **Discernment practice hours / week** — score 3, conf 0.51
  _The response acknowledges the user's experience but lacks depth in discernment practice analysis._
- **Compassion Fatigue** — score 2, conf 0.54
  _Assistant acknowledges compassion fatigue but does not express it personally._

**Turn 2 [user]:**  _honestly i feel like a fraud showing up._
- **Genuine** — score 4, conf 0.54
  _Speaker acknowledges their emotional state with honesty and vulnerability._
- **Seeking approval** — score 4, conf 0.54
  _Speaker expresses self-doubt and insecurity, seeking validation._
- **Honesty Humility** — score 4, conf 0.54
  _Speaker acknowledges emotional numbness and self-awareness of being a fraud._

**Turn 3 [assistant]:**  _You're not a fraud. The numbness is a coping system that activates after sustained loss; it doesn't undo years of meaningful care._
- **Patient care orientation** — score 4, conf 0.54
  _Assistant acknowledges clinical experience and emotional response in patient care._
- **Well-being component: Engagement** — score 4, conf 0.54
  _Assistant shows empathy and validation, aligning with engagement through compassion._
- **Psychological construct: Self-Compassion total** — score 4, conf 0.54
  _Assistant shows compassion and validation, aligning with self-compassion._

---

## Known limitations

Documented in detail in [`docs/DESIGN_DECISIONS.md`](../docs/DESIGN_DECISIONS.md), specifically sections 11-14. Summary:

- The scorer is intentionally conservative on speaker-vs-described disambiguation — assistant turns that *acknowledge* a user's emotion are correctly NOT attributed that emotion, but the model sometimes over-corrects and underscores facets the assistant *is* delivering (e.g. real Compassion in an empathic reply).
- Retrieval at `top_k=20` can miss a semantically relevant facet when the turn describes a state without naming the facet. Mitigation: raise top_k or add hybrid (BM25 + dense) retrieval.
- Confidence in this report is pseudo-calibrated. For real per-prediction calibration, run `scripts/run_calibration_appendix.py`.
