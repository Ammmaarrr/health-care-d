"""All LLM prompts in one place.

Keep these *small* and *strict*. The system's reliability lives or dies here.
"""
from __future__ import annotations


# --------------------------------------------------------------------------- #
# 1. Query → structured intent
# --------------------------------------------------------------------------- #
QUERY_PROMPT = """\
You convert a natural-language healthcare query into structured requirements.

Output ONLY valid JSON with this exact shape:
{
  "location": string | null,
  "state": string | null,
  "district": string | null,
  "rural": boolean | null,
  "required_capabilities": string[],
  "constraints": string[],
  "doctor_preference": "full-time" | "part-time" | null
}

Rules:
- `required_capabilities` must use only these tokens:
"icu", "emergency", "surgery", "anesthesiologist", "oxygen",
"oncology", "dialysis", "neonatal", "trauma", "lab", "imaging".

  Mapping hints:
  - "appendectomy", "operation", "OT", "operating theatre" -> "surgery".
  - "casualty", "ER", "emergency room", "24/7 care", "ambulance" -> "emergency".
  - "ventilator", "critical care", "intensive care" -> "icu".
  - "anesthesia", "anaesthesiology" -> "anesthesiologist".
  - "O2", "oxygen supply", "oxygen support" -> "oxygen".
  - "cancer", "chemotherapy", "chemo", "radiation therapy", "tumor",
    "tumour" -> "oncology".
  - "kidney failure", "haemodialysis", "hemodialysis", "renal",
    "nephrology" -> "dialysis".
  - "newborn", "premature", "NICU", "paediatric ICU" -> "neonatal".
  - "accident", "polytrauma", "head injury", "road accident" -> "trauma";
    if the user mentions both "trauma" and "emergency", include both.
  - "pathology", "blood test", "biochemistry", "haematology",
    "microbiology" -> "lab".
  - "x-ray", "X-ray", "MRI", "CT", "CT scan", "ultrasound", "sonography",
    "radiograph", "imaging" -> "imaging".

- LOCATION INFERENCE — when the user mentions a city / town only, set
  `state` to the Indian state that contains it. Use this lookup:
    Maharashtra: Mumbai, Pune, Nagpur, Nashik, Aurangabad, Thane,
                 Solapur, Kolhapur, Sangli, Amravati, Nanded, Akola
    Karnataka:   Bengaluru, Bangalore, Mysuru, Mysore, Mangaluru,
                 Hubli, Belagavi, Davangere
    Delhi:       Delhi, New Delhi
    Bihar:       Patna, Gaya, Muzaffarpur, Hajipur, Motihari, Bhagalpur,
                 Darbhanga, Purnia, Begusarai, Siwan, Aurangabad-Bihar,
                 Gopalganj, Rafiganj
    Rajasthan:   Jaipur, Udaipur, Jodhpur, Ajmer, Bikaner, Kota
    Uttar Pradesh: Lucknow, Kanpur, Varanasi, Allahabad, Prayagraj,
                   Agra, Meerut, Ghaziabad, Noida, Gorakhpur,
                   Bareilly, Aligarh, Mathura
    Tamil Nadu:  Chennai, Madurai, Coimbatore, Tiruchirappalli, Trichy,
                 Salem, Tirunelveli, Erode, Vellore
    West Bengal: Kolkata, Howrah, Siliguri, Asansol, Durgapur
    Telangana:   Hyderabad, Warangal, Karimnagar, Nizamabad
    Gujarat:     Ahmedabad, Surat, Vadodara, Rajkot, Bhavnagar, Gandhinagar
    Kerala:      Kochi, Cochin, Thiruvananthapuram, Trivandrum,
                 Kozhikode, Calicut, Thrissur, Kollam, Alappuzha
    Punjab:      Ludhiana, Amritsar, Jalandhar, Patiala
    Haryana:     Faridabad, Gurugram, Gurgaon, Rohtak, Hisar, Karnal
    Madhya Pradesh: Bhopal, Indore, Gwalior, Jabalpur, Ujjain
    Andhra Pradesh: Visakhapatnam, Vijayawada, Guntur, Tirupati
    Odisha:      Bhubaneswar, Cuttack, Rourkela
    Jharkhand:   Ranchi, Jamshedpur, Dhanbad, Bokaro
    Assam:       Guwahati, Dibrugarh, Silchar
    Chhattisgarh: Raipur, Bhilai
    Uttarakhand: Dehradun, Haridwar
    Chandigarh:  Chandigarh
  When you fill `state` from a city, ALSO set `district` to that city.

- `rural` is true ONLY if the query explicitly says "rural", "village",
  or names a small/known-rural area. Otherwise null.
- `doctor_preference` is "part-time" when the user says "part-time",
  "parttime", "visiting", or "on-call" doctors. It is "full-time" when
  they say "full-time", "resident", or "in-house" doctors. Otherwise null.
- `constraints` captures other requirements verbatim (e.g. "tertiary care",
  "within 50 km", "low cost").

Query: {query}

JSON:"""


# --------------------------------------------------------------------------- #
# 2. Capability extraction (the most important prompt in the system)
# --------------------------------------------------------------------------- #
EXTRACT_PROMPT = """\
You extract structured medical capabilities from a hospital's free-form notes.

Be STRICT and CONSERVATIVE:
- If a capability is not explicitly mentioned -> "uncertain".
- Do NOT infer. If the notes say "general medicine", do NOT mark surgery yes.
- "ICU available" / "intensive care unit" -> has_icu = "yes".
- "no ICU" / "ICU under construction" / "ICU planned" -> has_icu = "no".
- The same yes/no/uncertain rules apply to every capability below.

Capability vocabulary (use exactly these field names):
- has_icu               (ICU / intensive care / critical care / ventilator)
- has_emergency         (ER / casualty / 24x7 / ambulance)
- has_surgery           (surgical / operating theatre / appendectomy / etc.)
- has_anesthesiologist  (anesthesiologist on staff)
- has_oxygen            (oxygen supply / O2 cylinders / oxygen plant)
- has_oncology          (oncology / cancer / chemotherapy / radiation)
- has_dialysis          (dialysis / haemodialysis / nephrology / renal unit)
- has_neonatal          (NICU / neonatal / newborn / premature unit)
- has_trauma            (trauma / accident ward / polytrauma)
- has_lab               (laboratory / pathology / biochemistry / haematology)
- has_imaging           (X-ray / CT / MRI / ultrasound / radiograph)
- doctor_type           ("full-time", "part-time", or "unknown")

Output ONLY valid JSON with this exact shape:
{
  "has_icu":             "yes" | "no" | "uncertain",
  "has_emergency":       "yes" | "no" | "uncertain",
  "has_surgery":         "yes" | "no" | "uncertain",
  "has_anesthesiologist":"yes" | "no" | "uncertain",
  "has_oxygen":          "yes" | "no" | "uncertain",
  "has_oncology":        "yes" | "no" | "uncertain",
  "has_dialysis":        "yes" | "no" | "uncertain",
  "has_neonatal":        "yes" | "no" | "uncertain",
  "has_trauma":          "yes" | "no" | "uncertain",
  "has_lab":             "yes" | "no" | "uncertain",
  "has_imaging":         "yes" | "no" | "uncertain",
  "doctor_type":         "full-time" | "part-time" | "unknown",
  "evidence": {
    "icu":              string,
    "emergency":        string,
    "surgery":          string,
    "anesthesiologist": string,
    "oxygen":           string,
    "oncology":         string,
    "dialysis":         string,
    "neonatal":         string,
    "trauma":           string,
    "lab":              string,
    "imaging":          string,
    "doctor_type":      string
  }
}

Each evidence value MUST be a verbatim sentence/phrase copied from the notes
that supports your decision, or an empty string if "uncertain"/"unknown".

NOTES:
\"\"\"
{notes}
\"\"\"

JSON:"""


# --------------------------------------------------------------------------- #
# 3. Validator — checks for contradictions
# --------------------------------------------------------------------------- #
VALIDATOR_PROMPT = """\
You validate a hospital's claimed capabilities against medical standards.

Capabilities (extracted):
{capabilities}

Known medical requirements (from external sources):
{standards}

Apply these rules strictly:
- Surgery requires anesthesiologist + oxygen.
- Emergency requires oxygen.
- ICU requires ventilator OR explicit critical-care indicators (treat
  oxygen as a strong supporting signal).
- Oncology requires laboratory AND imaging support.
- Dialysis requires laboratory support.
- Neonatal/NICU requires oxygen.
- Trauma care requires emergency capability.

Output ONLY valid JSON:
{
  "issues": [
    { "capability": string, "issue": string, "severity": "low"|"medium"|"high" }
  ],
  "confidence_adjustment": number   // negative; 0 to -0.5
}

Be strict. Flag every contradiction. If none, return empty issues and 0.

JSON:"""


# --------------------------------------------------------------------------- #
# 4. Per-hospital ranking reasoning (short)
# --------------------------------------------------------------------------- #
RANK_PROMPT = """\
You write a one-sentence reasoning for why a hospital does or does not match
the user's query.

User query intent:
{parsed_query}

Hospital:
- Name: {name}
- Location: {location}
- Capabilities: {capabilities}
- Validator flags: {flags}

Write ONE sentence (max 30 words). Be specific. Cite missing requirements
if any. No filler words.

Reasoning:"""


# --------------------------------------------------------------------------- #
# 5. Trace simplifier — turns raw trace into UI-ready prose
# --------------------------------------------------------------------------- #
TRACE_PROMPT = """\
Convert this raw system trace into a clean, structured explanation for a
human reader. Keep it under 120 words.

Sections (use these exact headings):
1. What the user asked
2. What we found
3. Issues we detected
4. Why we ranked these hospitals
5. How we computed the trust score

Raw trace:
{trace_json}

Explanation:"""


# --------------------------------------------------------------------------- #
# 6. Tavily query generator
# --------------------------------------------------------------------------- #
TAVILY_QUERY_PROMPT = """\
Generate ONE concise web-search query to find the minimum requirements,
typical staffing, and equipment for: {capability}

Return only the search query string. No quotes, no explanation."""
