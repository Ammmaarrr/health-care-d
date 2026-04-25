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
  "constraints": string[]
}

Rules:
- `required_capabilities` must use only these tokens: \
"icu", "emergency", "surgery", "anesthesiologist", "oxygen".
- "appendectomy", "trauma", "operation", "OT" → "surgery".
- "casualty", "ER", "emergency room", "24/7 care" → "emergency".
- "ventilator", "critical care", "intensive care" → "icu".
- "anesthesia", "anaesthesiology" → "anesthesiologist".
- "O2", "oxygen supply", "oxygen support" → "oxygen".

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
- `constraints` captures other requirements verbatim (e.g. "part-time doctors",
  "tertiary care", "within 50 km").

Query: {query}

JSON:"""


# --------------------------------------------------------------------------- #
# 2. Capability extraction (the most important prompt in the system)
# --------------------------------------------------------------------------- #
EXTRACT_PROMPT = """\
You extract structured medical capabilities from a hospital's free-form notes.

Be STRICT and CONSERVATIVE:
- If a capability is not explicitly mentioned → "uncertain".
- Do NOT infer. If they say "general medicine", do NOT mark surgery as yes.
- If they say "ICU available" → has_icu = "yes".
- If they say "no ICU" / "ICU under construction" → has_icu = "no".

Output ONLY valid JSON with this exact shape:
{
  "has_icu":             "yes" | "no" | "uncertain",
  "has_emergency":       "yes" | "no" | "uncertain",
  "has_surgery":         "yes" | "no" | "uncertain",
  "has_anesthesiologist":"yes" | "no" | "uncertain",
  "has_oxygen":          "yes" | "no" | "uncertain",
  "doctor_type":         "full-time" | "part-time" | "unknown",
  "evidence": {
    "icu":              string,
    "emergency":        string,
    "surgery":          string,
    "anesthesiologist": string,
    "oxygen":           string,
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
- ICU requires ventilator OR explicit critical-care indicators.

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
