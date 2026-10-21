# Evaluation results

Generated 2026-10-21T19:27:50 · retrieval `lexical` · LLM off · 35 scenarios

> These numbers measure **software behaviour** against expectations derived from NHS / MedlinePlus / WHO patient pages. They are **not** a clinical validation: the scenarios and rules were written by the software author and have not been reviewed by clinicians, and the scenarios are short, scripted cases rather than real patient conversations.

| Metric | Result |
|---|---|
| Candidate-condition recall | 23/23 (100%) |
| Top-1 agreement | 11/11 (100%) |
| Set-aside respected | 2/2 (100%) |
| Red-flag sensitivity (emergency scenarios) | 10/10 (100%) |
| Red-flag specificity (non-emergency scenarios) | 25/25 (100%) |
| Correct refusal / out-of-scope | 4/4 (100%) |
| Urgency level as expected | 2/2 (100%) |
| Citation correctness (displayed citations) | 341/341 (100%) |
| Evidence-grounding rate (statements) | 322/322 (100%) |
| Scenario expectations traceable to corpus | 35/35 (100%) |

Mean follow-up questions per completed scenario: 5.9

| Scenario | Category | Lang | Stage | Listed conditions | Urgency | Result |
|---|---|---|---|---|---|---|
| cold_en_typical | typical | en | assessment | common_cold, allergic_rhinitis, sore_throat | self_care | pass |
| cold_hi_typical | typical | hi | assessment | common_cold, allergic_rhinitis, sore_throat | self_care | pass |
| allergy_hi_dust | typical | hi | assessment | allergic_rhinitis | self_care | pass |
| overlap_nose_short | overlap | en | assessment | common_cold, allergic_rhinitis | self_care | pass |
| overlap_mucus_example | overlap | hi | assessment | common_cold, allergic_rhinitis | self_care | pass |
| flu_en | typical | en | assessment | flu_like_illness | self_care | pass |
| sinus_en | typical | en | assessment | sinusitis, common_cold, allergic_rhinitis | self_care | pass |
| throat_hi | typical | hi | assessment | sore_throat, common_cold | self_care | pass |
| acidity_hi | typical | hi | assessment | indigestion | self_care | pass |
| acidity_en | typical | en | assessment | indigestion | self_care | pass |
| constipation_hi | typical | hi | assessment | constipation | soon | pass |
| tension_en | typical | en | assessment | tension_headache | soon | pass |
| migraine_hi | typical | hi | assessment | migraine | self_care | pass |
| headache_ambiguous | ambiguous | en | assessment | — | soon | pass |
| contact_derm_en | typical | en | assessment | contact_dermatitis | self_care | pass |
| hives_en | typical | en | assessment | hives | self_care | pass |
| heat_rash_hi | typical | hi | assessment | heat_rash | self_care | pass |
| skin_overlap | overlap | hi | assessment | hives | self_care | pass |
| em_chest_pain_hi | emergency | hi | emergency | — | — | pass |
| em_acidity_radiating | emergency | en | emergency | — | — | pass |
| em_stroke_en | emergency | en | emergency | — | — | pass |
| em_thunderclap_hi | emergency | hi | emergency | — | — | pass |
| em_breathing_hi | emergency | hi | emergency | — | — | pass |
| em_anaphylaxis_en | emergency | en | emergency | — | — | pass |
| em_meningitis_combo | emergency | hi | emergency | — | — | pass |
| em_dengue_warning | emergency | hi | emergency | — | — | pass |
| em_sore_throat_drool | emergency | en | emergency | — | — | pass |
| em_vomit_blood | emergency | hi | emergency | — | — | pass |
| nf_nose_breathing | false_alarm_check | en | assessment | common_cold, allergic_rhinitis | self_care | pass |
| nf_negated_chest | false_alarm_check | hi | assessment | indigestion | self_care | pass |
| refuse_fatigue_only | refuse | en | assessment | — | soon | pass |
| refuse_out_of_scope | refuse | hi | assessment | — | soon | pass |
| refuse_child | refuse | en | assessment | — | soon | pass |
| urgent_blood_stool | urgent | en | assessment | constipation | urgent | pass |
| soon_fever_long | urgent | en | assessment | flu_like_illness | soon | pass |
