<p align="center">
  <img src="./assets/images/HEADLYN-BLUE-LOGO.png" alt="Headlyn Logo" width="280" />
</p>

# Headlyn

Headlyn is a news intelligence project that turns fragmented article streams into a structured, story-first feed. The product goal is to group related articles about the same event into one evolving story while preserving source attribution.

## Dataset Files

- Source-specific article JSON files: `assets/datasets/articles/`
- Master clustering evaluation dataset:
  `assets/datasets/articles/clustering-evaluation.json`
- Scraped article HTML: `assets/datasets/raw-html/`
- RSS snapshots: `assets/rss-feeds/raw/`

## Evaluation Cluster Catalogue

The `C01`–`C08` groups are the gold-positive event clusters: all six articles in
each group should be recognized as coverage of the same story. The `S01`–`S08`
groups are singleton hard negatives: they reuse an entity, institution, or broad
topic from a core cluster but describe a different story and should not be
merged into that core cluster.

### Core Event Clusters

<details>
<summary><code>C01_KARNATAKA_RESIGNATION</code> — Karnataka leadership transition (dev; 6 articles, 5 sources)</summary>

**Story:** Karnataka Chief Minister Siddaramaiah announced that he would resign,
triggering a Congress leadership transition toward D.K. Shivakumar.

- **News18:** [Siddaramaiah Announces Resignation At Karnataka Cabinet Meet: 'High Command Will Decide Next CM'](https://www.news18.com/india/siddaramaiah-confirms-his-resignation-as-chief-minister-to-karnataka-cabinet-karnataka-power-buzz-10116744.html)
- **News18:** [‘CM Resignation Syndrome’: BJP’s Dig At Congress After Siddaramaiah Announces Exit](https://www.news18.com/india/syndrome-of-cm-resigning-continues-bjp-takes-dig-at-congress-after-siddaramaiah-confirms-resignation-basavaraj-bommai-dk-shivakumar-chief-minister-power-struggle-ws-l-10116811.html)
- **NDTV:** ["High Command Asked": Siddaramaiah Gets Emotional After Resigning](https://www.ndtv.com/india-news/siddaramaiah-announces-he-will-resign-at-breakfast-meeting-with-dk-shivakumar-11558047#publisher=newsstand)
- **Hindustan Times:** [Siddaramaiah confirms resignation to Karnataka cabinet, all eyes on Shivakumar now](https://www.hindustantimes.com/india-news/siddaramaiah-to-resign-as-karnataka-cm-at-3-pm-today-all-eyes-on-shivakumar-now-sources-101779945393557.html)
- **The Hindu:** [Karnataka CM Siddaramaiah announces decision to step down at breakfast meeting with Ministers](https://www.thehindu.com/news/national/karnataka/siddaramaiah-informs-cabinet-colleagues-of-decision-to-step-down-as-karnataka-cm-official-sources/article71032264.ece)
- **Firstpost:** [Siddaramaiah announces resignation, says Congress high command will pick next Karnataka CM](https://www.firstpost.com/india/siddaramaiah-announces-resignation-says-congress-high-command-will-pick-next-karnataka-cm-14016177.html)

</details>

<details>
<summary><code>C02_CBSE_OSM</code> — CBSE on-screen marking controversy (dev; 6 articles, 3 sources)</summary>

**Story:** Claims of security flaws and marking discrepancies in CBSE Class 12
on-screen marking prompted denials, official responses, and scrutiny of the
technology vendor.

- **News18:** [CBSE Sets Record Straight: Board Rejects Social Media Claims Over Coempt Eduteck Exam Evaluation Contract](https://www.news18.com/education-career/cbse-sets-record-straight-board-rejects-social-media-claims-over-coempt-eduteck-exam-evaluation-contract-10116129.html)
- **Hindustan Times:** [CBSE test website had 'master password' that could be used to tamper marks, claims 'hacker' Nisarga Adhikary](https://www.hindustantimes.com/india-news/cbse-osm-portal-had-master-password-that-could-be-used-to-tamper-marks-claims-hacker-nisarga-adhikary-101779937467585.html)
- **NDTV:** [CBSE OSM System Student-Centric, Discrepancies Will Be Rectified: Dharmendra Pradhan](https://www.ndtv.com/education/cbse-osm-system-student-centric-discrepancies-will-be-rectified-dharmendra-pradhan-11558307#publisher=newsstand)
- **Hindustan Times:** [Telangana firm Coempt Edutech in focus amid CBSE-OSM row](https://www.hindustantimes.com/india-news/telangana-firm-coempt-edutech-in-focus-amid-cbse-osm-row-rahul-gandhi-101779942293536.html)
- **NDTV:** [CBSE Officials Told Principals To Defend Class 12 Evaluation System After Result Row](https://www.ndtv.com/education/cbse-officials-told-principals-to-defend-class-12-osm-evaluation-system-after-result-row-11558449#publisher=newsstand)
- **News18:** [CBSE Cybersecurity Put To The Test: 19-Year-Old Ethical Hacker Flags 'OSM Portal Flaws'](https://www.news18.com/india/cbse-cybersecurity-put-to-the-test-19-year-old-ethical-hacker-flags-osm-portal-flaws-10114058.html)

</details>

<details>
<summary><code>C03_SC_SIR_VERDICT</code> — Supreme Court SIR verdict (dev; 6 articles, 4 sources)</summary>

**Story:** The Supreme Court upheld the Election Commission's authority to
conduct Special Intensive Revision of electoral rolls and issued a major
constitutional ruling on the exercise.

- **NDTV:** [In Big Win For Election Commission, Supreme Court Says "SIR Breathes Life Into Constitution"](https://www.ndtv.com/india-news/supreme-court-says-sir-exercise-breathes-life-into-constitution-11553085/amp/1)
- **News18:** [‘Linked To Free And Fair Polls’: Five SC Observations That Dismantle Opposition's Anti-SIR Argument](https://www.news18.com/india/linked-to-free-and-fair-polls-five-sc-observations-that-dismantle-oppositions-anti-sir-argument-ws-l-10114808.html)
- **Hindustan Times:** [Election Commission acted within powers in SIR exercise, Supreme Court says](https://www.hindustantimes.com/india-news/election-commission-acted-within-powers-in-sir-exercise-supreme-court-says-special-intensive-revision-101779945077722.html)
- **News18:** [‘Political, Moral And Constitutional Defeat’: BJP Targets Opposition After SC SIR Verdict](https://www.news18.com/india/political-moral-and-constitutional-defeat-bjp-targets-opposition-after-sc-sir-verdict-ws-l-10115276.html)
- **Firstpost:** [Supreme Court upholds Election Commission’s right to conduct SIR in Bihar](https://www.firstpost.com/india/supreme-court-election-commission-sir-bihar-14015707.html)
- **Hindustan Times:** [To vote is a ‘valuable constitutional right’ but not absolute: Supreme Court in SIR verdict](https://www.hindustantimes.com/india-news/right-to-vote-is-a-valuable-constitutional-right-but-not-absolute-supreme-court-in-sir-verdict-cji-surya-kant-101779931850510.html)

</details>

<details>
<summary><code>C04_PINARAYI_ED_RAIDS</code> — ED raids linked to Pinarayi Vijayan (dev; 6 articles, 4 sources)</summary>

**Story:** The Enforcement Directorate raided premises linked to former Kerala
Chief Minister Pinarayi Vijayan and his daughter Veena in the Exalogic-CMRL
case, prompting protests and political reactions.

- **NDTV:** [Probe Into Pinarayi Vijayan's Daughter's Firm, Dealings Widens Amid Protests](https://www.ndtv.com/india-news/probe-into-pinarayi-vijayans-daughter-veenas-firm-dealings-widens-amid-protests-11558498#publisher=newsstand)
- **Hindustan Times:** [Violence erupts as ED raids for Kerala CM Pinarayi Vijayan’s houses](https://www.hindustantimes.com/india-news/violence-erupts-as-ed-raids-for-kerala-cm-pinarayi-vijayan-houses-101779933404217.html)
- **NDTV:** ["Planned Attack": Kerala Minister On Violence During Raids At Pinarayi Vijayan's Home](https://www.ndtv.com/india-news/planned-attack-kerala-minister-on-violence-during-raids-at-pinarayi-vijayans-home-11558221#publisher=newsstand)
- **The Hindu:** [CPI(M) condemns ED raids on Pinarayi Vijayan, calls for protests in Andhra Pradesh](https://www.thehindu.com/news/national/andhra-pradesh/cpim-condemns-ed-raids-on-pinarayi-vijayan-calls-for-protests-in-andhra-pradesh/article71029675.ece)
- **News18:** [‘Would Give Satisfaction To Rahul Gandhi’: Pinarayi Vijayan On ED Raids At Kerala Residences](https://www.news18.com/india/would-give-satisfaction-to-rahul-gandhi-pinarayi-vijayan-on-ed-raids-at-kerala-residences-ws-l-10115601.html)
- **News18:** [ED Raids Former Kerala CM Pinarayi Vijayan’s Residence In Case Linked To Daughter's Firm](https://www.news18.com/india/ed-raids-former-kerala-chief-minister-pinarayi-vijayan-residence-veena-vijayan-exalogic-company-case-thiruvananthapuram-10114445.html)

</details>

<details>
<summary><code>C05_TWISHA_BAIL</code> — Twisha Sharma anticipatory-bail ruling (test; 6 articles, 4 sources)</summary>

**Story:** The Madhya Pradesh High Court quashed retired judge Giribala Singh's
anticipatory bail in the Twisha Sharma death case, citing concerns including
possible evidence tampering.

- **NDTV:** [Twisha Sharma's Mother-In-Law Might Have Tampered Forensic Evidence: Court](https://www.ndtv.com/india-news/twisha-sharmas-mother-in-law-giribala-singh-might-have-tampered-forensic-evidence-court-11557854#publisher=newsstand)
- **The Hindu:** [Twisha Sharma death case: Madhya Pradesh HC quashes anticipatory bail of retired judge Giribala Singh](https://www.thehindu.com/news/national/madhya-pradesh/twisha-sharma-death-case-madhya-pradesh-hc-quashes-anticipatory-bail-giribala-singh/article71030927.ece)
- **Hindustan Times:** [Twisha Sharma's mother-in-law Giribala Singh seen feeding stray dog after quashed anticipatory bail](https://www.hindustantimes.com/india-news/twisha-sharmas-mother-in-law-giribala-singh-seen-feeding-stray-dog-after-quashed-anticipatory-bail-101779946583752.html)
- **News18:** [Twisha Sharma Death: Giribala Singh's Anticipatory Bail Quashed By Madhya Pradesh HC](https://www.news18.com/india/twisha-sharma-death-giribala-singhs-anticipatory-bail-quashed-by-madhya-pradesh-hc-ws-l-10116377.html)
- **News18:** [Twisha Sharma's Post-Mortem Suggests Injuries Caused By 'Scuffle' Prior To Death, MP Govt Tells HC](https://www.news18.com/india/twisha-dowry-death-case-mp-govt-tells-hc-ex-judge-giribala-singh-son-subjected-her-to-cruelty-ws-l-10115553.html)
- **Hindustan Times:** [Twisha Sharma case: MP high court quashes Giribala Singh’s anticipatory bail](https://www.hindustantimes.com/india-news/twisha-sharma-case-mp-high-court-quashes-giribala-singh-s-anticipatory-bail-101779938651926.html)

</details>

<details>
<summary><code>C06_QUAD_DELHI_MEETING</code> — Delhi Quad foreign ministers meeting (test; 6 articles, 4 sources)</summary>

**Story:** Quad foreign ministers met in New Delhi and announced initiatives on
maritime surveillance, port infrastructure, critical minerals, energy security,
and counter-terrorism, followed by related diplomatic announcements.

- **Firstpost:** [Fiji sees Quad port initiative as boost for billion-dollar Suva redevelopment plan](https://www.firstpost.com/world/fiji-sees-quad-port-initiative-as-boost-for-billion-dollar-suva-redevelopment-plan-14015816.html)
- **The Hindu:** [No specific port project identified, says Fiji’s Foreign Minister, day after Quad Foreign Ministers pledge assistance](https://www.thehindu.com/news/national/fiji-port-project-infrastructure-quad-foreign-ministers-declare-assistance/article71030889.ece)
- **Hindustan Times:** [Surveillance, minerals and energy: What are the key takeaways from Delhi QUAD meet](https://www.hindustantimes.com/india-news/surveillance-minerals-and-energy-what-are-the-key-takways-from-delhi-quad-meet-101779779527689.html)
- **News18:** [PM Modi To Visit Australia In 'Near Future', Says Foreign Minister Penny Wong After Quad Meet](https://www.news18.com/india/pm-modi-to-visit-australia-in-near-future-says-foreign-minister-penny-wong-after-quad-meet-ws-l-10113853.html)
- **Hindustan Times:** [PM Modi to visit Australia in ‘near future’: Australian foreign minister Penny Wong](https://www.hindustantimes.com/india-news/pm-modi-to-visit-australia-in-near-future-australian-foreign-minister-penny-wong-101779792129790.html)
- **News18:** [QUAD Foreign Ministers Condemn Pahalgam, Bondi Beach Terror Attacks, Slam Cross-Border Terrorism](https://www.news18.com/india/quad-foreign-ministers-condemn-pahalgam-bondi-beach-terror-attacks-slam-cross-border-terrorism-ws-l-10113225.html)

</details>

<details>
<summary><code>C07_NEET_LEAK_RESPONSE</code> — NEET-UG leak investigation and re-exam (test; 6 articles, 5 sources)</summary>

**Story:** The NEET-UG 2026 paper-leak investigation advanced with fresh arrests
and a proposed witness while authorities prepared the nationwide
re-examination.

- **News18:** [NEET Paper Leak: CBI To Turn Latur Coaching Owner’s Son, Who Appeared For Exam, Into ‘Star Witness’](https://www.news18.com/india/neet-paper-leak-cbi-to-turn-latur-coaching-owners-son-who-appeared-for-exam-into-star-witness-ws-l-10114569.html)
- **News18:** [CBI Arrests Latur-Based Doctor, Pune Physics Teacher In NEET-UG Leak Case; 13 Held So Far](https://www.news18.com/india/cbi-arrests-latur-based-doctor-pune-physics-teacher-in-neet-ug-leak-case-13-held-so-far-ws-l-10114759.html)
- **NDTV:** [NEET UG 2026 Re-exam: NTA Extends Fee Refund Bank Details Submission Deadline](https://www.ndtv.com/education/neet-ug-2026-re-exam-date-2026-nta-extends-fee-refund-bank-details-submission-deadline-11558258#publisher=newsstand)
- **Hindustan Times:** [Latur doc, Pune teacher held in NEET case; total arrests 13](https://www.hindustantimes.com/cities/mumbai-news/latur-doc-pune-teacher-held-in-neet-case-total-arrests-13-101779909297614.html)
- **The Hindu:** [CBI arrests Latur-based doctor and Pune Physics teacher in NEET-UG 2026 case](https://www.thehindu.com/news/national/cbi-arrests-latur-based-doctor-and-pune-physics-teacher-in-neet-ug-2026-case/article71027814.ece)
- **PIB:** [Union Education Minister reviews preparedness for NEET-UG 2026 Re-Examination](https://pib.gov.in/PressReleaseIframePage.aspx?PRID=2266029)

</details>

<details>
<summary><code>C08_WANGCHUK_FAST</code> — Sonam Wangchuk hunger strike (test; 6 articles, 3 sources)</summary>

**Story:** On day 19 of Sonam Wangchuk's hunger strike over examination
irregularities, courts, government, opposition parties, and civil-society
supporters responded to mounting health concerns.

- **News18:** [Can Sonam Wangchuk Be Arrested For Hunger Strike At Jantar Mantar? What The Law Says](https://www.news18.com/explainers/as-sonam-wangchuks-fast-enters-day-19-is-hunger-strike-legal-in-india-what-the-law-says-ws-l-10215489.html)
- **The Hindu:** [Congress urges Wangchuk to end his fast, says Opposition party to keep pressing Dharmendra Pradhan’s resignation](https://www.thehindu.com/news/national/congress-appeal-sonam-wangchuk-fast-jantar-mantar-protest-neet-education-minister-resignation/article71229635.ece)
- **News18:** [Centre's First Response To Sonam Wangchuk's Hunger Strike: ‘Will Provide Medical Care On Doctors' Advice’](https://www.news18.com/india/centres-first-response-to-sonam-wangchuks-hunger-strike-will-provide-medical-care-on-doctors-advice-ws-l-10215911.html)
- **The Hindu:** [‘Save Sonam Wangchuk’: Hyderabad civil society groups hold candlelight vigil, demand action on NEET row](https://www.thehindu.com/news/national/telangana/save-sonam-wangchuk-hyderabad-civil-society-groups-hold-candlelight-vigil-demand-action-on-neet-row/article71230534.ece)
- **Hindustan Times:** [Government's first reaction to Sonam Wangchuk's hunger strike](https://www.hindustantimes.com/india-news/govt-first-reaction-sonam-wangchuk-hunger-strike-health-medical-assistance-doctor-report-cjp-abhijit-dipke-delhi-hc-101784181791723.html)
- **Hindustan Times:** ['Every life is precious': Delhi HC tells Centre over plea seeking Sonam Wangchuk's force-feeding](https://www.hindustantimes.com/india-news/every-life-is-precious-delhi-high-court-hc-tells-centre-to-monitor-sonam-wangchuk-health-daily-101784181004734.html)

</details>

### Hard-Negative Singleton Clusters

<details>
<summary><code>S01_KARNATAKA_CASTE_SURVEY</code> — Karnataka caste survey (dev)</summary>

**Different story:** Siddaramaiah receives Karnataka's caste survey report amid
the leadership-change coverage.

- **The Hindu:** [Amid leadership change developments, Karnataka CM receives caste survey report](https://www.thehindu.com/news/national/karnataka/karnataka-cm-siddaramaiah-receives-caste-survey-report/article71029538.ece)
- **Designed to challenge:** `C01_KARNATAKA_RESIGNATION`

</details>

<details>
<summary><code>S02_CBSE_LANGUAGE_POLICY</code> — CBSE language policy case (dev)</summary>

**Different story:** The Supreme Court examines whether CBSE's three-language
rule is unreasonable for children and school resources.

- **The Hindu:** [Supreme Court to examine if CBSE’s three-language rule is ‘unreasonable’ on kids, resources](https://www.thehindu.com/news/national/supreme-court-seeks-centre-ncerts-responses-on-plea-against-cbses-three-language-rule-for-class-9-students/article71029041.ece)
- **Designed to challenge:** `C02_CBSE_OSM`

</details>

<details>
<summary><code>S03_HARYANA_SIR_STRATEGY</code> — Haryana Congress SIR strategy (dev)</summary>

**Different story:** A Haryana Congress panel meets to plan its political
strategy around SIR rather than reporting the Supreme Court verdict itself.

- **The Hindu:** [Haryana Congress panel meets to chalk out strategy on SIR](https://www.thehindu.com/news/national/haryana/haryana-congress-panel-meets-to-chalk-out-strategy-on-sir/article71030311.ece)
- **Designed to challenge:** `C03_SC_SIR_VERDICT`

</details>

<details>
<summary><code>S04_ED_CADRE_EXPANSION</code> — Enforcement Directorate staffing (dev)</summary>

**Different story:** The Finance Ministry approves an Enforcement Directorate
cadre expansion, unrelated to the Kerala raids.

- **Hindustan Times:** [Finance ministry approves cadre expansion in Enforcement Directorate](https://www.hindustantimes.com/india-news/finance-ministry-approves-cadre-expansion-in-enforcement-directorate-101779939312083.html)
- **Designed to challenge:** `C04_PINARAYI_ED_RAIDS`

</details>

<details>
<summary><code>S05_UGC_NET_CENTRES</code> — UGC NET exam centres (test)</summary>

**Different story:** NTA adds UGC NET exam centres in the North-East and permits
city-preference revisions, separate from the NEET leak and re-exam.

- **NDTV:** [UGC NET 2026: New Exam Centres Added In North-East, City Preference Revision Allowed](https://www.ndtv.com/education/nta-adds-new-exam-centres-in-north-east-allows-candidates-to-revise-city-preferences-11557914#publisher=newsstand)
- **Designed to challenge:** `C07_NEET_LEAK_RESPONSE`

</details>

<details>
<summary><code>S06_TWISHA_OPINION</code> — Twisha Sharma opinion article (test)</summary>

**Different story:** An opinion article uses the Twisha Sharma case to discuss
posthumous character scrutiny of women without reporting the later
anticipatory-bail ruling.

- **News18:** [Twisha Sharma Case: Why Dowry Deaths Often Turn Into Posthumous Character Trials Of Women](https://www.news18.com/explainers/twisha-sharma-case-why-dowry-deaths-often-turn-into-posthumous-character-trials-of-women-shil-ws-l-10114753.html)
- **Designed to challenge:** `C05_TWISHA_BAIL`

</details>

<details>
<summary><code>S07_JAPAN_FM_FOOD</code> — Japanese foreign minister's India visit (test)</summary>

**Different story:** Japanese Foreign Minister Motegi samples Indian food during
his visit rather than reporting the Quad meeting and its policy outcomes.

- **Firstpost:** ['It’s very sweet, like a donut': Japanese FM Motegi enjoys gulab jamun, filter coffee during India visit](https://www.firstpost.com/india/its-very-sweet-like-a-donut-japanese-fm-motegi-enjoys-gulab-jamun-filter-coffee-during-india-visit-watch-14015684.html)
- **Designed to challenge:** `C06_QUAD_DELHI_MEETING`

</details>

<details>
<summary><code>S08_WANGCHUK_SECMOL_PROFILE</code> — Sonam Wangchuk's SECMOL profile (test)</summary>

**Different story:** A profile of Sonam Wangchuk's SECMOL campus shares the same
central person but does not concern his hunger strike.

- **News18:** [No Bells, Student-Run Campus: Why Sonam Wangchuk's SECMOL Feels Like A School From The Future](https://www.news18.com/india/no-bells-student-run-campus-why-sonam-wangchuks-secmol-feels-like-a-school-from-the-future-10216439.html)
- **Designed to challenge:** `C08_WANGCHUK_FAST`

</details>

## Target Product Features

- **One story, many sources**: group related articles into a single story so users do not see the same event repeated across publishers.
- **Cleaner news feed**: focus the feed on distinct stories instead of scattered article duplicates.
- **Evolving story updates**: update stories as new information becomes available.
- **Personalized ranking**: learn from user behavior to show more relevant stories first.
- **Better discovery**: keep the feed fresh and diverse beyond a user's usual interests.
