/* Interface languages: English (source), हिन्दी, தமிழ்.
   The English text itself is the key. Any element whose whole text (or placeholder / title / aria-label) matches a key
   is shown in the chosen language, including text the pages create later. Numbers, IDs and names are never changed.
   Translations are a first draft; have a native speaker review them before official use. */
"use strict";
const LANGS = [["en", "English"], ["hi", "हिन्दी"], ["ta", "தமிழ்"]];
const LANG = (() => {
  const q = new URLSearchParams(location.search).get("lang");
  try {
    if (q && LANGS.some(([c]) => c === q)) localStorage.setItem("lang", q);
    const v = localStorage.getItem("lang");
    return LANGS.some(([c]) => c === v) ? v : "en";
  } catch (e) { return q || "en"; }
})();

// [English, Hindi, Tamil]
const T_ROWS = [
  // ---------- shell, sign-in, roles
  ["Parcel Reconciliation Console", "भूखंड मिलान कंसोल", "நிலப் பதிவு பொருத்தக் கன்சோல்"],
  ["Cadastral ↔ revenue layers · SIH26013", "भू-सर्वेक्षण ↔ राजस्व परतें · SIH26013", "நில அளவை ↔ வருவாய் அடுக்குகள் · SIH26013"],
  ["Dashboard", "डैशबोर्ड", "முகப்பு"],
  ["Review queue", "समीक्षा कतार", "மதிப்பாய்வு வரிசை"],
  ["Map explorer", "मानचित्र", "வரைபடம்"],
  ["Data quality", "डेटा गुणवत्ता", "தரவுத் தரம்"],
  ["Changes", "परिवर्तन", "மாற்றங்கள்"],
  ["Real data", "वास्तविक डेटा", "உண்மைத் தரவு"],
  ["Match your data", "अपना डेटा मिलाएँ", "உங்கள் தரவைப் பொருத்துக"],
  ["Audit log", "ऑडिट लॉग", "தணிக்கைப் பதிவு"],
  ["Methodology", "कार्यप्रणाली", "வழிமுறை"],
  ["Administration", "प्रशासन", "நிர்வாகம்"],
  ["Sign in", "साइन इन करें", "உள்நுழைக"],
  ["Sign out", "साइन आउट", "வெளியேறு"],
  ["Username", "उपयोगकर्ता नाम", "பயனர் பெயர்"],
  ["Password", "पासवर्ड", "கடவுச்சொல்"],
  ["Language", "भाषा", "மொழி"],
  ["Demo accounts", "डेमो खाते", "டெமோ கணக்குகள்"],
  ["For the hackathon demo only. Disable these in Administration before any real use.",
   "केवल हैकाथॉन डेमो के लिए। वास्तविक उपयोग से पहले प्रशासन में इन्हें बंद करें।",
   "ஹேக்கத்தான் டெமோவுக்கு மட்டும். உண்மையான பயன்பாட்டுக்கு முன் நிர்வாகத்தில் இவற்றை முடக்கவும்."],
  ["Each role sees its own pages. What you can do is checked on the server, not only hidden on screen.",
   "हर भूमिका को अपने ही पेज दिखते हैं। आप क्या कर सकते हैं, यह सर्वर पर जाँचा जाता है, केवल स्क्रीन पर छिपाया नहीं जाता।",
   "ஒவ்வொரு பொறுப்புக்கும் அதற்கான பக்கங்கள் மட்டுமே தெரியும். நீங்கள் செய்யக்கூடியவை சர்வரில் சரிபார்க்கப்படுகின்றன, திரையில் மறைக்கப்படுவது மட்டுமல்ல."],
  ["Role", "भूमिका", "பொறுப்பு"],
  ["Use", "उपयोग करें", "பயன்படுத்து"],
  ["Sign-in failed.", "साइन इन विफल रहा।", "உள்நுழைவு தோல்வியடைந்தது."],
  ["Please sign in.", "कृपया साइन इन करें।", "தயவுசெய்து உள்நுழையவும்."],
  ["Revenue officer", "राजस्व अधिकारी", "வருவாய் அலுவலர்"],
  ["Supervisor", "पर्यवेक्षक", "மேற்பார்வையாளர்"],
  ["Auditor", "लेखा परीक्षक", "தணிக்கையாளர்"],
  ["System administrator", "सिस्टम प्रशासक", "கணினி நிர்வாகி"],
  ["Loading…", "लोड हो रहा है…", "ஏற்றுகிறது…"],
  ["Close", "बंद करें", "மூடு"],
  ["Nothing here.", "यहाँ कुछ नहीं है।", "இங்கு எதுவும் இல்லை."],
  ["None yet.", "अभी कोई नहीं।", "இன்னும் இல்லை."],
  ["No match", "कोई मेल नहीं", "பொருத்தம் இல்லை"],

  // ---------- statuses and link words
  ["Auto-resolved", "स्वतः हल", "தானாகத் தீர்ந்தது"],
  ["Needs review", "समीक्षा आवश्यक", "மதிப்பாய்வு தேவை"],
  ["No counterpart", "कोई समकक्ष नहीं", "இணை இல்லை"],
  ["No counterpart found", "कोई समकक्ष नहीं मिला", "இணை கிடைக்கவில்லை"],
  ["Auto-accepted", "स्वतः स्वीकृत", "தானாக ஏற்கப்பட்டது"],
  ["Auto-accepted (outline overlap)", "स्वतः स्वीकृत (रूपरेखा मेल)", "தானாக ஏற்கப்பட்டது (வரைவுப் பொருத்தம்)"],
  ["Auto (overlap)", "स्वतः (मेल)", "தானாக (பொருத்தம்)"],
  ["Accepted", "स्वीकृत", "ஏற்கப்பட்டது"],
  ["Rejected", "अस्वीकृत", "நிராகரிக்கப்பட்டது"],
  ["Accepted by officer", "अधिकारी द्वारा स्वीकृत", "அலுவலரால் ஏற்கப்பட்டது"],
  ["Rejected by officer", "अधिकारी द्वारा अस्वीकृत", "அலுவலரால் நிராகரிக்கப்பட்டது"],
  ["Linked", "जुड़ा", "இணைக்கப்பட்டது"],
  ["Part of a larger shape", "बड़े आकार का हिस्सा", "பெரிய வடிவத்தின் பகுதி"],
  ["Covers several shapes", "कई आकारों को ढकता है", "பல வடிவங்களை உள்ளடக்கியது"],
  ["Review", "समीक्षा", "மதிப்பாய்வு"],
  ["Auto", "स्वतः", "தானியங்கி"],
  ["Unmatched", "बेमेल", "பொருந்தாதவை"],
  ["Decided", "निर्णीत", "முடிவானவை"],
  ["High", "उच्च", "உயர்"],
  ["Medium", "मध्यम", "நடுத்தர"],
  ["Low", "निम्न", "குறைவு"],

  // ---------- review queue
  ["About this data", "इस डेटा के बारे में", "இந்தத் தரவு பற்றி"],
  ["Reveal ground truth (demo)", "सही उत्तर दिखाएँ (डेमो)", "சரியான விடையைக் காட்டு (டெமோ)"],
  ["Show hand checks", "हाथ से जाँच दिखाएँ", "கைச் சரிபார்ப்புகளைக் காட்டு"],
  ["Synthetic test", "कृत्रिम परीक्षण", "செயற்கைச் சோதனை"],
  ["Real: OSM ↔ Microsoft", "वास्तविक: OSM ↔ Microsoft", "உண்மை: OSM ↔ Microsoft"],
  ["Calibrated match probability", "अंशांकित मिलान संभावना", "அளவீடு செய்யப்பட்ட பொருத்த நிகழ்தகவு"],
  ["likely not a link", "संभवतः मेल नहीं", "பெரும்பாலும் இணை அல்ல"],
  ["needs a person", "व्यक्ति की ज़रूरत", "ஒருவர் பார்க்க வேண்டும்"],
  ["auto-accept", "स्वतः स्वीकार", "தானாக ஏற்பு"],
  ["Evidence", "प्रमाण", "சான்று"],
  ["Overlap of outlines (IoU)", "रूपरेखाओं का मेल (IoU)", "வரைவுகளின் பொருத்தம் (IoU)"],
  ["Distance between centres", "केंद्रों के बीच दूरी", "மையங்களுக்கு இடையிலான தூரம்"],
  ["Similarity of areas", "क्षेत्रफल की समानता", "பரப்பளவு ஒற்றுமை"],
  ["Owner (cadastral)", "स्वामी (भू-सर्वेक्षण)", "உரிமையாளர் (நில அளவை)"],
  ["Owner (revenue)", "स्वामी (राजस्व)", "உரிமையாளர் (வருவாய்)"],
  ["Name similarity (shown, not scored)", "नाम समानता (केवल दिखाई गई, अंक में नहीं)", "பெயர் ஒற்றுமை (காட்டப்படுகிறது, மதிப்பெண்ணில் இல்லை)"],
  ["Why the model says this", "मॉडल ऐसा क्यों कहता है", "மாதிரி ஏன் இப்படிச் சொல்கிறது"],
  ["Bars to the right push toward “same parcel”, to the left away from it.",
   "दाईं ओर की पट्टियाँ “एक ही भूखंड” की ओर ले जाती हैं, बाईं ओर की उससे दूर।",
   "வலப்பக்கப் பட்டைகள் “ஒரே மனை” என்பதை நோக்கித் தள்ளும், இடப்பக்கம் அதிலிருந்து விலக்கும்."],
  ["Officer decision", "अधिकारी का निर्णय", "அலுவலர் முடிவு"],
  ["Officer decision (recorded)", "अधिकारी का निर्णय (दर्ज)", "அலுவலர் முடிவு (பதிவானது)"],
  ["Optional note for the audit trail", "ऑडिट के लिए वैकल्पिक टिप्पणी", "தணிக்கைக்கான விருப்பக் குறிப்பு"],
  ["Reason for changing the decision (required)", "निर्णय बदलने का कारण (आवश्यक)", "முடிவை மாற்றுவதற்கான காரணம் (கட்டாயம்)"],
  ["Accept link (A)", "मिलान स्वीकार करें (A)", "இணைப்பை ஏற்கவும் (A)"],
  ["Reject link (R)", "मिलान अस्वीकार करें (R)", "இணைப்பை நிராகரிக்கவும் (R)"],
  ["Change to Accept", "स्वीकार में बदलें", "ஏற்புக்கு மாற்று"],
  ["Change to Reject", "अस्वीकार में बदलें", "நிராகரிப்புக்கு மாற்று"],
  ["Accepted ✓", "स्वीकृत ✓", "ஏற்கப்பட்டது ✓"],
  ["Rejected ✓", "अस्वीकृत ✓", "நிராகரிக்கப்பட்டது ✓"],
  ["Decision logged.", "निर्णय दर्ज हुआ।", "முடிவு பதிவானது."],
  ["Decision changed and logged.", "निर्णय बदला और दर्ज हुआ।", "முடிவு மாற்றப்பட்டுப் பதிவானது."],
  ["Add a reason in the note box to change an earlier decision.", "पिछला निर्णय बदलने के लिए टिप्पणी में कारण लिखें।", "முந்தைய முடிவை மாற்ற குறிப்புப் பெட்டியில் காரணம் எழுதவும்."],
  ["Recorded decisions can only be changed by a supervisor.", "दर्ज निर्णय केवल पर्यवेक्षक बदल सकते हैं।", "பதிவான முடிவுகளை மேற்பார்வையாளர் மட்டுமே மாற்ற முடியும்."],
  ["A decision can be changed only with a written reason. Every change is kept in the audit log.",
   "निर्णय केवल लिखित कारण के साथ बदला जा सकता है। हर बदलाव ऑडिट लॉग में रहता है।",
   "எழுத்து மூலம் காரணம் கொடுத்தால் மட்டுமே முடிவை மாற்ற முடியும். ஒவ்வொரு மாற்றமும் தணிக்கைப் பதிவில் இருக்கும்."],
  ["J / K or ↓ / ↑ moves through the list.", "J / K या ↓ / ↑ से सूची में आगे-पीछे जाएँ।", "J / K அல்லது ↓ / ↑ மூலம் பட்டியலில் நகரவும்."],
  ["Review queue is clear. Every remaining link was resolved automatically.",
   "समीक्षा कतार खाली है। बाकी सभी मिलान स्वतः हल हो गए।",
   "மதிப்பாய்வு வரிசை காலியாக உள்ளது. மீதமுள்ள அனைத்து இணைப்புகளும் தானாகத் தீர்க்கப்பட்டன."],
  ["Select a parcel on the map or a tab on the left.", "मानचित्र पर भूखंड या बाईं ओर कोई टैब चुनें।", "வரைபடத்தில் ஒரு மனையை அல்லது இடப்பக்கத் தாவலைத் தேர்ந்தெடுக்கவும்."],
  ["No candidate above the review threshold", "समीक्षा सीमा से ऊपर कोई उम्मीदवार नहीं", "மதிப்பாய்வு வரம்புக்கு மேல் வேட்பாளர் இல்லை"],
  ["Not in the hand-checked sample.", "हाथ से जाँचे गए नमूने में नहीं।", "கையால் சரிபார்த்த மாதிரியில் இல்லை."],
  ["Hand check: the SAME building (checked against satellite imagery).", "हाथ से जाँच: एक ही इमारत (उपग्रह चित्र से जाँचा गया)।", "கைச் சரிபார்ப்பு: ஒரே கட்டடம் (செயற்கைக்கோள் படத்துடன் சரிபார்க்கப்பட்டது)."],
  ["Hand check: NOT the same building.", "हाथ से जाँच: एक ही इमारत नहीं।", "கைச் சரிபார்ப்பு: ஒரே கட்டடம் அல்ல."],
  ["Ground truth: this IS the same parcel.", "सही उत्तर: यह एक ही भूखंड है।", "சரியான விடை: இது ஒரே மனை."],
  ["Ground truth: this is NOT the same parcel.", "सही उत्तर: यह एक ही भूखंड नहीं है।", "சரியான விடை: இது ஒரே மனை அல்ல."],
  ["Ground truth: genuinely missing from the revenue layer.", "सही उत्तर: राजस्व परत में वास्तव में अनुपस्थित।", "சரியான விடை: வருவாய் அடுக்கில் உண்மையிலேயே இல்லை."],
  ["These are reported rather than force-matched, so no geometry is invented.", "इन्हें ज़बरदस्ती मिलाने के बजाय दर्ज किया जाता है, ताकि कोई आकृति गढ़ी न जाए।", "இவை வலிந்து பொருத்தப்படாமல் தெரிவிக்கப்படுகின்றன; எனவே எந்த வடிவமும் புனையப்படுவதில்லை."],
  ["Satellite (needs internet)", "उपग्रह चित्र (इंटरनेट चाहिए)", "செயற்கைக்கோள் படம் (இணையம் தேவை)"],
  ["Basemap (needs internet)", "आधार मानचित्र (इंटरनेट चाहिए)", "அடிப்படை வரைபடம் (இணையம் தேவை)"],
  ["Revenue layer", "राजस्व परत", "வருவாய் அடுக்கு"],
  ["Microsoft (offset removed)", "Microsoft (खिसकाव हटाया गया)", "Microsoft (இடப்பெயர்ச்சி நீக்கப்பட்டது)"],
  ["cadastral parcels", "भू-सर्वेक्षण भूखंड", "நில அளவை மனைகள்"],
  ["OSM buildings", "OSM इमारतें", "OSM கட்டடங்கள்"],
  ["resolved without a person", "बिना व्यक्ति के हल", "மனிதர் இன்றித் தீர்ந்தவை"],
  ["linked without a person", "बिना व्यक्ति के जुड़े", "மனிதர் இன்றி இணைந்தவை"],
  ["auto-accept precision", "स्वतः स्वीकार की परिशुद्धता", "தானியங்கு ஏற்பின் துல்லியம்"],
  ["auto-link precision (hand-checked)", "स्वतः मिलान की परिशुद्धता (हाथ से जाँची)", "தானியங்கு இணைப்புத் துல்லியம் (கைச் சரிபார்ப்பு)"],
  ["awaiting review", "समीक्षा बाकी", "மதிப்பாய்வுக்குக் காத்திருப்பவை"],
  ["links decided", "निर्णीत मिलान", "முடிவான இணைப்புகள்"],
  ["links decided in total", "कुल निर्णीत मिलान", "மொத்தம் முடிவான இணைப்புகள்"],
  ["decisions by you", "आपके निर्णय", "உங்கள் முடிவுகள்"],
  ["hash chain verified ✓", "हैश श्रृंखला सत्यापित ✓", "ஹாஷ் சங்கிலி சரிபார்க்கப்பட்டது ✓"],

  // ---------- map explorer
  ["Data", "डेटा", "தரவு"],
  ["Find a parcel", "भूखंड खोजें", "மனையைத் தேடுக"],
  ["Parcel ID or owner name", "भूखंड ID या स्वामी का नाम", "மனை ID அல்லது உரிமையாளர் பெயர்"],
  ["Building ID (O… or M…)", "इमारत ID (O… या M…)", "கட்டட ID (O… அல்லது M…)"],
  ["Cadastral layer", "भू-सर्वेक्षण परत", "நில அளவை அடுக்கு"],
  ["Other layers", "अन्य परतें", "பிற அடுக்குகள்"],
  ["Click a parcel on the map, or search for one.", "मानचित्र पर भूखंड पर क्लिक करें या उसे खोजें।", "வரைபடத்தில் ஒரு மனையைச் சொடுக்கவும் அல்லது தேடவும்."],
  ["Cadastral parcel", "भू-सर्वेक्षण भूखंड", "நில அளவை மனை"],
  ["Revenue parcel", "राजस्व भूखंड", "வருவாய் மனை"],
  ["OSM building", "OSM इमारत", "OSM கட்டடம்"],
  ["Microsoft footprint", "Microsoft रूपरेखा", "Microsoft வரைவு"],
  ["Owner on record", "दर्ज स्वामी", "பதிவிலுள்ள உரிமையாளர்"],
  ["Candidate links shown", "दिखाए गए संभावित मिलान", "காட்டப்படும் வேட்பாளர் இணைப்புகள்"],
  ["Candidate links", "संभावित मिलान", "வேட்பாளர் இணைப்புகள்"],
  ["Harmonised record", "एकीकृत अभिलेख", "ஒருங்கிணைந்த பதிவு"],
  ["Probability", "संभावना", "நிகழ்தகவு"],
  ["Status", "स्थिति", "நிலை"],
  ["Open in review", "समीक्षा में खोलें", "மதிப்பாய்வில் திற"],
  ["Owner (revenue record)", "स्वामी (राजस्व अभिलेख)", "உரிமையாளர் (வருவாய்ப் பதிவு)"],
  ["Patta no. / survey no.", "पट्टा सं. / सर्वे सं.", "பட்டா எண் / புல எண்"],
  ["Tax assessment no.", "कर निर्धारण सं.", "வரி மதிப்பீட்டு எண்"],
  ["Land use", "भूमि उपयोग", "நிலப் பயன்பாடு"],
  ["Surveyed area", "सर्वेक्षित क्षेत्रफल", "அளக்கப்பட்ட பரப்பு"],
  ["Recorded area (revenue)", "दर्ज क्षेत्रफल (राजस्व)", "பதிவுப் பரப்பு (வருவாய்)"],
  ["Plinth area (tax)", "कुर्सी क्षेत्रफल (कर)", "அடித்தளப் பரப்பு (வரி)"],
  ["Link type", "मिलान प्रकार", "இணைப்பு வகை"],
  ["Sources", "स्रोत", "மூலங்கள்"],

  // ---------- real data and hand checks
  ["Real data: three independent building maps", "वास्तविक डेटा: तीन स्वतंत्र इमारत मानचित्र", "உண்மைத் தரவு: மூன்று தனித்த கட்டட வரைபடங்கள்"],
  ["Buildings mapped", "मानचित्रित इमारतें", "வரைபடமாக்கப்பட்ட கட்டடங்கள்"],
  ["OSM buildings found in Microsoft", "Microsoft में मिली OSM इमारतें", "Microsoft-இல் கண்ட OSM கட்டடங்கள்"],
  ["Microsoft buildings missing in OSM", "OSM में अनुपस्थित Microsoft इमारतें", "OSM-இல் இல்லாத Microsoft கட்டடங்கள்"],
  ["candidates to add to the map", "मानचित्र में जोड़ने योग्य", "வரைபடத்தில் சேர்க்கத் தக்கவை"],
  ["Map offset removed", "मानचित्र खिसकाव हटाया गया", "வரைபட இடப்பெயர்ச்சி நீக்கப்பட்டது"],
  ["Road-space encroachment", "सड़क क्षेत्र पर अतिक्रमण", "சாலைப் பகுதி ஆக்கிரமிப்பு"],
  ["Map", "मानचित्र", "வரைபடம்"],
  ["Satellite", "उपग्रह चित्र", "செயற்கைக்கோள் படம்"],
  ["Road reserve (estimated)", "सड़क आरक्षित क्षेत्र (अनुमानित)", "சாலை ஒதுக்கீட்டுப் பகுதி (மதிப்பீடு)"],
  ["Remove map offset (co-registration)", "मानचित्र खिसकाव हटाएँ (सह-पंजीकरण)", "வரைபட இடப்பெயர்ச்சியை நீக்கு (இணைப் பதிவு)"],
  ["Check pairs by hand", "जोड़ों को हाथ से जाँचें", "இணைகளைக் கையால் சரிபார்க்கவும்"],
  ["Is the blue outline (OSM) the same building as the orange one? The model's answer is hidden so your check stays independent.",
   "क्या नीली रूपरेखा (OSM) और नारंगी रूपरेखा एक ही इमारत है? मॉडल का उत्तर छिपा है ताकि आपकी जाँच स्वतंत्र रहे।",
   "நீல வரைவு (OSM) ஆரஞ்சு வரைவின் அதே கட்டடமா? உங்கள் சரிபார்ப்பு சார்பற்றதாக இருக்க மாதிரியின் விடை மறைக்கப்பட்டுள்ளது."],
  ["Same building", "एक ही इमारत", "ஒரே கட்டடம்"],
  ["Different", "अलग", "வேறு"],
  ["Can't tell", "कह नहीं सकते", "சொல்ல முடியவில்லை"],
  ["All sampled pairs checked. Thank you.", "सभी नमूना जोड़े जाँचे गए। धन्यवाद।", "அனைத்து மாதிரி இணைகளும் சரிபார்க்கப்பட்டன. நன்றி."],
  ["Your role views the results; officers and supervisors do the checking.", "आपकी भूमिका परिणाम देखती है; जाँच अधिकारी और पर्यवेक्षक करते हैं।", "உங்கள் பொறுப்பு முடிவுகளைப் பார்ப்பது; சரிபார்ப்பை அலுவலர்களும் மேற்பார்வையாளர்களும் செய்வார்கள்."],
  ["Accuracy on real data", "वास्तविक डेटा पर सटीकता", "உண்மைத் தரவில் துல்லியம்"],
  ["How the sources disagree", "स्रोत कैसे असहमत हैं", "மூலங்கள் எவ்வாறு வேறுபடுகின்றன"],
  ["Descriptions of real disagreement, not accuracy figures.", "वास्तविक असहमति का विवरण, सटीकता के आँकड़े नहीं।", "உண்மையான வேறுபாட்டின் விவரம்; துல்லிய எண்கள் அல்ல."],
  ["OSM buildings confirmed by other sources", "अन्य स्रोतों द्वारा पुष्ट OSM इमारतें", "பிற மூலங்கள் உறுதிப்படுத்திய OSM கட்டடங்கள்"],
  ["Possible encroachment on road space", "सड़क क्षेत्र पर संभावित अतिक्रमण", "சாலைப் பகுதியில் சாத்தியமான ஆக்கிரமிப்பு"],
  ["Is the confidence honest on real data?", "क्या वास्तविक डेटा पर विश्वास-स्तर सही है?", "உண்மைத் தரவில் நம்பகத்தன்மை சரியானதா?"],
  ["Rule", "नियम", "விதி"],
  ["Precision (95% range)", "परिशुद्धता (95% सीमा)", "துல்லியம் (95% வரம்பு)"],
  ["Precision", "परिशुद्धता", "துல்லியம்"],
  ["Recall", "प्राप्ति (रिकॉल)", "மீட்பு (ரீகால்)"],
  ["Pairs predicted", "अनुमानित जोड़े", "கணிக்கப்பட்ட இணைகள்"],
  ["Model probability", "मॉडल संभावना", "மாதிரி நிகழ்தகவு"],
  ["Checked", "जाँचे गए", "சரிபார்த்தவை"],
  ["Model said (mean)", "मॉडल का अनुमान (औसत)", "மாதிரி கூறியது (சராசரி)"],
  ["Actually same", "वास्तव में एक", "உண்மையில் ஒன்றே"],
  ["Model, auto-accept", "मॉडल, स्वतः स्वीकार", "மாதிரி, தானியங்கு ஏற்பு"],
  ["Model, accept or review", "मॉडल, स्वीकार या समीक्षा", "மாதிரி, ஏற்பு அல்லது மதிப்பாய்வு"],
  ["Plain IoU matching", "साधारण IoU मिलान", "சாதாரண IoU பொருத்தம்"],
  ["Model or IoU (combined)", "मॉडल या IoU (संयुक्त)", "மாதிரி அல்லது IoU (இணைந்தது)"],
  ["IoU without co-registration", "सह-पंजीकरण के बिना IoU", "இணைப் பதிவு இல்லாத IoU"],
  ["Source", "स्रोत", "மூலம்"],
  ["Building", "इमारत", "கட்டடம்"],
  ["Overlap", "अतिव्यापन", "மேற்பொருந்தல்"],
  ["Share of building", "इमारत का हिस्सा", "கட்டடத்தின் பங்கு"],
  ["Two sources agree", "दो स्रोत सहमत", "இரு மூலங்கள் ஒப்புக்கொள்கின்றன"],
  ["Yes", "हाँ", "ஆம்"],
  ["Sources", "स्रोत", "மூலங்கள்"],
  ["Linked automatically", "स्वतः जुड़े", "தானாக இணைந்தவை"],
  ["Sent to review", "समीक्षा को भेजे", "மதிப்பாய்வுக்கு அனுப்பியவை"],
  ["Only in first", "केवल पहले में", "முதலாவதில் மட்டும்"],
  ["Only in second", "केवल दूसरे में", "இரண்டாவதில் மட்டும்"],
  ["Median IoU", "माध्यिका IoU", "இடைநிலை IoU"],

  // ---------- upload
  ["Match your own layers", "अपनी परतें मिलाएँ", "உங்கள் அடுக்குகளைப் பொருத்துக"],
  ["Upload", "अपलोड", "பதிவேற்று"],
  ["GeoJSON, GeoPackage, or a zipped Shapefile. Up to 25 MB and 20,000 shapes per layer.",
   "GeoJSON, GeoPackage या ज़िप किया Shapefile। प्रति परत 25 MB और 20,000 आकृतियों तक।",
   "GeoJSON, GeoPackage அல்லது சுருக்கப்பட்ட Shapefile. ஒரு அடுக்குக்கு 25 MB, 20,000 வடிவங்கள் வரை."],
  ["Layer A (reference)", "परत A (संदर्भ)", "அடுக்கு A (குறிப்பு)"],
  ["Layer B (to compare)", "परत B (तुलना के लिए)", "அடுக்கு B (ஒப்பிட)"],
  ["Remove the offset between the layers first (co-registration)", "पहले परतों के बीच का खिसकाव हटाएँ (सह-पंजीकरण)", "முதலில் அடுக்குகளுக்கிடையிலான இடப்பெயர்ச்சியை நீக்கு (இணைப் பதிவு)"],
  ["Match the layers", "परतें मिलाएँ", "அடுக்குகளைப் பொருத்து"],
  ["Reading, aligning and matching…", "पढ़ना, संरेखित करना और मिलाना…", "படித்து, சீரமைத்து, பொருத்துகிறது…"],
  ["Recent uploads", "हाल के अपलोड", "சமீபத்திய பதிவேற்றங்கள்"],
  ["Result", "परिणाम", "முடிவு"],
  ["Shapes", "आकृतियाँ", "வடிவங்கள்"],
  ["Offset removed", "खिसकाव हटाया गया", "இடப்பெயர்ச்சி நீக்கப்பட்டது"],
  ["an officer decides", "अधिकारी निर्णय करता है", "அலுவலர் முடிவு செய்வார்"],
  ["Links found", "मिले मिलान", "கண்ட இணைப்புகள்"],
  ["Download links (CSV)", "मिलान डाउनलोड करें (CSV)", "இணைப்புகளைப் பதிவிறக்கு (CSV)"],
  ["Linked by", "किससे जुड़ा", "இணைத்தது"],
  ["Model", "मॉडल", "மாதிரி"],
  ["Overlap (IoU)", "मेल (IoU)", "பொருத்தம் (IoU)"],
  ["Offset", "खिसकाव", "இடப்பெயர்ச்சி"],

  // ---------- changes
  ["Real change, 2016 → 2023", "वास्तविक परिवर्तन, 2016 → 2023", "உண்மை மாற்றம், 2016 → 2023"],
  ["Built since 2016", "2016 के बाद बनी", "2016-க்குப் பின் கட்டப்பட்டவை"],
  ["Possibly demolished", "संभवतः ध्वस्त", "இடிக்கப்பட்டிருக்கலாம்"],
  ["Grew taller", "ऊँची हुई", "உயரம் கூடியவை"],
  ["confirmed", "पुष्ट", "உறுதி"],
  ["unconfirmed", "अपुष्ट", "உறுதியில்லை"],
  ["not in OSM", "OSM में नहीं", "OSM-இல் இல்லை"],
  ["field check", "क्षेत्र जाँच", "களச் சரிபார்ப்பு"],
  ["New building", "नई इमारत", "புதிய கட்டடம்"],
  ["Demolished", "ध्वस्त", "இடிக்கப்பட்டது"],
  ["Altered / extended", "परिवर्तित / विस्तारित", "மாற்றப்பட்டது / விரிவாக்கப்பட்டது"],
  ["Download changes (GeoJSON)", "परिवर्तन डाउनलोड करें (GeoJSON)", "மாற்றங்களைப் பதிவிறக்கு (GeoJSON)"],

  // ---------- dashboard, quality, audit, method, admin: headings and key labels
  ["Ward overview", "वार्ड अवलोकन", "வார்டு கண்ணோட்டம்"],
  ["Open review queue", "समीक्षा कतार खोलें", "மதிப்பாய்வு வரிசையைத் திற"],
  ["Explore the map", "मानचित्र देखें", "வரைபடத்தைப் பார்"],
  ["Resolved without a person", "बिना व्यक्ति के हल", "மனிதர் இன்றித் தீர்ந்தவை"],
  ["Cadastral parcels", "भू-सर्वेक्षण भूखंड", "நில அளவை மனைகள்"],
  ["Awaiting review", "समीक्षा बाकी", "மதிப்பாய்வுக்குக் காத்திருப்பவை"],
  ["Links decided by officers", "अधिकारियों द्वारा निर्णीत मिलान", "அலுவலர்கள் முடிவு செய்த இணைப்புகள்"],
  ["Every module of the problem statement, measured", "समस्या कथन का हर मॉड्यूल, मापा गया", "சிக்கல் அறிக்கையின் ஒவ்வொரு கூறும், அளக்கப்பட்டது"],
  ["Recent officer decisions", "हाल के अधिकारी निर्णय", "சமீபத்திய அலுவலர் முடிவுகள்"],
  ["Model vs baseline", "मॉडल बनाम आधार रेखा", "மாதிரி எதிர் அடிப்படை"],
  ["Calibrated model", "अंशांकित मॉडल", "அளவீடு செய்த மாதிரி"],
  ["Confidence", "विश्वास-स्तर", "நம்பகத்தன்மை"],
  ["Confidence 0–100", "विश्वास-स्तर 0–100", "நம்பகத்தன்மை 0–100"],
  ["Topology errors, revenue layer", "टोपोलॉजी त्रुटियाँ, राजस्व परत", "இடவியல் பிழைகள், வருவாய் அடுக்கு"],
  ["Coordinate systems handled", "संभाली गई निर्देशांक प्रणालियाँ", "கையாளப்பட்ட ஆய அமைப்புகள்"],
  ["Columns recognised", "पहचाने गए कॉलम", "அடையாளம் கண்ட நெடுவரிசைகள்"],
  ["Units detected", "पहचानी गई इकाइयाँ", "கண்டறியப்பட்ட அலகுகள்"],
  ["Parcels with a conflict", "विरोधाभास वाले भूखंड", "முரண்பாடு உள்ள மனைகள்"],
  ["Harmonised layer (GeoJSON)", "एकीकृत परत (GeoJSON)", "ஒருங்கிணைந்த அடுக்கு (GeoJSON)"],
  ["Harmonised table (CSV)", "एकीकृत तालिका (CSV)", "ஒருங்கிணைந்த அட்டவணை (CSV)"],
  ["Conflicts (CSV)", "विरोधाभास (CSV)", "முரண்பாடுகள் (CSV)"],
  ["Search parcel, officer or note", "भूखंड, अधिकारी या टिप्पणी खोजें", "மனை, அலுவலர் அல்லது குறிப்பைத் தேடுக"],
  ["All decisions", "सभी निर्णय", "அனைத்து முடிவுகள்"],
  ["Show changed decisions", "बदले गए निर्णय दिखाएँ", "மாற்றப்பட்ட முடிவுகளைக் காட்டு"],
  ["Download CSV", "CSV डाउनलोड करें", "CSV பதிவிறக்கு"],
  ["Download raw log (.jsonl)", "मूल लॉग डाउनलोड करें (.jsonl)", "மூலப் பதிவைப் பதிவிறக்கு (.jsonl)"],
  ["No decisions yet. Decisions made in the review queue appear here.", "अभी कोई निर्णय नहीं। समीक्षा कतार में किए निर्णय यहाँ दिखेंगे।", "இன்னும் முடிவுகள் இல்லை. மதிப்பாய்வு வரிசையில் எடுக்கும் முடிவுகள் இங்கு தோன்றும்."],
  ["How it works and how it was tested", "यह कैसे काम करता है और कैसे जाँचा गया", "இது எப்படி இயங்குகிறது, எப்படிச் சோதிக்கப்பட்டது"],
  ["Pipeline", "प्रक्रिया क्रम", "செயல்முறை வரிசை"],
  ["Tested on real maps: hand-checked pairs", "वास्तविक मानचित्रों पर परीक्षण: हाथ से जाँचे जोड़े", "உண்மை வரைபடங்களில் சோதனை: கையால் சரிபார்த்த இணைகள்"],
  ["Synthetic stress tests", "कृत्रिम दबाव परीक्षण", "செயற்கை அழுத்தச் சோதனைகள்"],
  ["What these numbers do and don't show", "ये आँकड़े क्या दिखाते हैं और क्या नहीं", "இந்த எண்கள் எதைக் காட்டுகின்றன, எதைக் காட்டவில்லை"],
  ["User accounts", "उपयोगकर्ता खाते", "பயனர் கணக்குகள்"],
  ["Add a user", "उपयोगकर्ता जोड़ें", "பயனரைச் சேர்"],
  ["Add user", "उपयोगकर्ता जोड़ें", "பயனரைச் சேர்"],
  ["Full name", "पूरा नाम", "முழுப் பெயர்"],
  ["Name", "नाम", "பெயர்"],
  ["Can see", "देख सकते हैं", "பார்க்கலாம்"],
  ["Active", "सक्रिय", "செயலில்"],
  ["Disabled", "निष्क्रिय", "முடக்கப்பட்டது"],
  ["Disable", "निष्क्रिय करें", "முடக்கு"],
  ["Enable", "सक्रिय करें", "இயக்கு"],
  ["Recent sign-ins and account changes", "हाल के साइन इन और खाता बदलाव", "சமீபத்திய உள்நுழைவுகளும் கணக்கு மாற்றங்களும்"],
  ["Data and policy", "डेटा और नीति", "தரவும் கொள்கையும்"],
  // ---------- model explanation labels
  ["Overlap of the two outlines", "दोनों रूपरेखाओं का मेल", "இரு வரைவுகளின் பொருத்தம்"],
  ["Shape / position difference", "आकार / स्थिति का अंतर", "வடிவ / இட வேறுபாடு"],
  // ---------- page introductions
  ["OpenStreetMap, Microsoft and Google each mapped the same buildings independently, and they disagree. Nothing here is planted. Accuracy comes only from pairs people have checked by hand against satellite imagery.",
   "OpenStreetMap, Microsoft और Google ने एक ही इमारतों को अलग-अलग मानचित्रित किया है, और वे आपस में मेल नहीं खाते। यहाँ कुछ भी गढ़ा नहीं गया है। सटीकता केवल उन जोड़ों से आती है जिन्हें लोगों ने उपग्रह चित्रों से हाथ से जाँचा है।",
   "OpenStreetMap, Microsoft, Google ஆகியவை ஒரே கட்டடங்களைத் தனித்தனியாக வரைபடமாக்கியுள்ளன; அவை ஒன்றுக்கொன்று வேறுபடுகின்றன. இங்கு எதுவும் புனையப்படவில்லை. துல்லியம், செயற்கைக்கோள் படங்களுடன் மக்கள் கையால் சரிபார்த்த இணைகளிலிருந்து மட்டுமே வருகிறது."],
  ["Upload two maps of the same area (for example a cadastral layer and a municipal or building layer). The system removes the offset between them, links the matching shapes and shows what it could and couldn't link. Nothing is changed in your files.",
   "एक ही क्षेत्र के दो मानचित्र अपलोड करें (जैसे भू-सर्वेक्षण परत और नगरपालिका या इमारत परत)। सिस्टम उनके बीच का खिसकाव हटाता है, मेल खाती आकृतियों को जोड़ता है और दिखाता है कि क्या जुड़ा और क्या नहीं। आपकी फ़ाइलें नहीं बदली जातीं।",
   "ஒரே பகுதியின் இரு வரைபடங்களைப் பதிவேற்றுங்கள் (எ.கா. நில அளவை அடுக்கும் நகராட்சி அல்லது கட்டட அடுக்கும்). அமைப்பு அவற்றுக்கிடையிலான இடப்பெயர்ச்சியை நீக்கி, பொருந்தும் வடிவங்களை இணைத்து, எது இணைந்தது, எது இணையவில்லை என்பதைக் காட்டும். உங்கள் கோப்புகள் மாற்றப்படாது."],
  ["Satellite imagery: Esri World Imagery (needs internet). Without internet the outlines still show.",
   "उपग्रह चित्र: Esri World Imagery (इंटरनेट चाहिए)। इंटरनेट के बिना भी रूपरेखाएँ दिखती हैं।",
   "செயற்கைக்கோள் படம்: Esri World Imagery (இணையம் தேவை). இணையம் இல்லாவிட்டாலும் வரைவுகள் தெரியும்."],
  ["Judge from the imagery: same roof, same structure? Small shifts between the outlines are normal.",
   "चित्र से तय करें: एक ही छत, एक ही ढाँचा? रूपरेखाओं में थोड़ा खिसकाव सामान्य है।",
   "படத்திலிருந்து முடிவு செய்யுங்கள்: ஒரே கூரை, ஒரே கட்டமைப்பா? வரைவுகளுக்கிடையே சிறு இடப்பெயர்ச்சி இயல்பானது."],
  ["also show the orange outline at its original position", "नारंगी रूपरेखा को उसकी मूल जगह पर भी दिखाएँ", "ஆரஞ்சு வரைவை அதன் அசல் இடத்திலும் காட்டு"],
  ["= both outlines describe the same structure, even if one is shifted, bigger, smaller or a slightly different shape.",
   "= दोनों रूपरेखाएँ एक ही ढाँचे की हैं, भले ही एक खिसकी, बड़ी, छोटी या थोड़े अलग आकार की हो।",
   "= இரு வரைவுகளும் ஒரே கட்டமைப்பைக் குறிக்கின்றன; ஒன்று நகர்ந்தோ, பெரிதாகவோ, சிறிதாகவோ, சற்று வேறு வடிவத்திலோ இருந்தாலும்."],
  ["= they are two separate structures (for example, the orange outline is really the neighbouring building).",
   "= ये दो अलग ढाँचे हैं (जैसे नारंगी रूपरेखा असल में पड़ोसी इमारत की है)।",
   "= இவை இரு தனிக் கட்டமைப்புகள் (எ.கா. ஆரஞ்சு வரைவு உண்மையில் அடுத்த கட்டடத்தைச் சேர்ந்தது)."],
  ["= the imagery doesn't settle it.", "= चित्र से तय नहीं होता।", "= படத்திலிருந்து முடிவு செய்ய முடியவில்லை."],
];
const T_MAP = new Map(T_ROWS.map((r) => [r[0], { hi: r[1], ta: r[2] }]));

// Sentences with numbers or names in them: [pattern, Hindi template, Tamil template]; $1, $2 … are the captured parts.
const T_PATTERNS = [
  [/^You have checked (\d+) of (\d+) pairs\.$/, "आपने $2 में से $1 जोड़े जाँचे हैं।", "$2 இணைகளில் $1 ஐ நீங்கள் சரிபார்த்துள்ளீர்கள்."],
  [/^([\d.]+) m apart · overlap ([\d.]+) · area ([\d.]+)$/, "$1 मी दूर · मेल $2 · क्षेत्रफल $3", "$1 மீ இடைவெளி · பொருத்தம் $2 · பரப்பு $3"],
  [/^Accepted by (.+)$/, "$1 द्वारा स्वीकृत", "$1 ஏற்றார்"],
  [/^Rejected by (.+)$/, "$1 द्वारा अस्वीकृत", "$1 நிராகரித்தார்"],
  [/^Built since (\d{4}), ([\d,]+) m²$/, "$1 के बाद बनी, $2 मी²", "$1-க்குப் பின் கட்டப்பட்டது, $2 மீ²"],
  [/^Possibly demolished, ([\d,]+) m²$/, "संभवतः ध्वस्त, $1 मी²", "இடிக்கப்பட்டிருக்கலாம், $1 மீ²"],
  [/^Built since (\d{4}) \((\d+)\)$/, "$1 के बाद बनी ($2)", "$1-க்குப் பின் கட்டப்பட்டவை ($2)"],
  [/^Possibly demolished \((\d+)\)$/, "संभवतः ध्वस्त ($1)", "இடிக்கப்பட்டிருக்கலாம் ($1)"],
  [/^Grew taller \((\d+)\)$/, "ऊँची हुई ($1)", "உயரம் கூடியவை ($1)"],
  [/^(OSM|Cadastral) · auto-resolved$/, "$1 · स्वतः हल", "$1 · தானாகத் தீர்ந்தது"],
  [/^(OSM|Cadastral) · needs review$/, "$1 · समीक्षा आवश्यक", "$1 · மதிப்பாய்வு தேவை"],
  [/^(OSM|Cadastral) · no counterpart$/, "$1 · कोई समकक्ष नहीं", "$1 · இணை இல்லை"],
  [/^Real: (\d{4}) → (\d{4})$/, "वास्तविक: $1 → $2", "உண்மை: $1 → $2"],
  [/^Synthetic test \(exact scores\)$/, "कृत्रिम परीक्षण (सटीक अंक)", "செயற்கைச் சோதனை (துல்லிய மதிப்பெண்கள்)"],
  [/^(\d+) by model · (\d+) by overlap$/, "$1 मॉडल से · $2 मेल से", "$1 மாதிரியால் · $2 பொருத்தத்தால்"],
  [/^(\d+) with no counterpart$/, "$1 बिना समकक्ष", "$1 இணை இல்லாதவை"],
  [/^Share of (cadastral|revenue|OSM|Microsoft) parcel covered$/, "$1 भूखंड का ढका हिस्सा", "$1 மனையின் மூடப்பட்ட பங்கு"],
  [/^Gap to the nearest competitor \((cadastral|revenue|OSM|Microsoft)\)$/, "निकटतम प्रतिस्पर्धी से अंतर ($1)", "அருகிலுள்ள போட்டியாளருடன் இடைவெளி ($1)"],
  [/^Closest-candidate rank \((cadastral|revenue|OSM|Microsoft) side\)$/, "निकटतम उम्मीदवार क्रम ($1)", "அருகிலுள்ள வேட்பாளர் தரம் ($1)"],
  [/^Competing candidates \((cadastral|revenue|OSM|Microsoft) side\)$/, "प्रतिस्पर्धी उम्मीदवार ($1)", "போட்டி வேட்பாளர்கள் ($1)"],
  [/^Audit log · (\d+) entr(?:y|ies) ·$/, "ऑडिट लॉग · $1 प्रविष्टियाँ ·", "தணிக்கைப் பதிவு · $1 பதிவுகள் ·"],
  [/^Auto-linked when the model gives ≥ (\d+%) or the outlines overlap \(IoU\) ≥ ([\d.]+) after the map offset is removed\. Checked against (\d+) hand-labelled pairs\.$/,
   "मॉडल ≥ $1 दे या खिसकाव हटाने के बाद रूपरेखाएँ ≥ $2 (IoU) मेल खाएँ तो स्वतः जुड़ता है। $3 हाथ से जाँचे जोड़ों पर परखा गया।",
   "மாதிரி ≥ $1 தந்தால் அல்லது இடப்பெயர்ச்சி நீக்கிய பின் வரைவுகள் ≥ $2 (IoU) பொருந்தினால் தானாக இணைக்கப்படும். $3 கைச் சரிபார்த்த இணைகளுடன் சோதிக்கப்பட்டது."],
  [/^This pair scored ([\d.]+%)\. Auto-accept needs ≥ ([\d.]+%) here \(threshold from this pair's spatial fold, calibrated to (\d+%) precision on held-out data\)\.$/,
   "इस जोड़े का अंक $1 है। यहाँ स्वतः स्वीकार के लिए ≥ $2 चाहिए (इस क्षेत्र-खंड की सीमा, अलग रखे डेटा पर $3 परिशुद्धता के लिए अंशांकित)।",
   "இந்த இணையின் மதிப்பெண் $1. இங்கு தானியங்கு ஏற்புக்கு ≥ $2 தேவை (இந்தப் பகுதியின் வரம்பு, தனியாக வைத்த தரவில் $3 துல்லியத்துக்கு அளவீடு செய்யப்பட்டது)."],
  [/^Pair (\S+) ↔ (\S+): blue = (\w+), orange = (\w+)(?: \(moved to remove the map offset\))?\.$/, "जोड़ा $1 ↔ $2: नीला = $3, नारंगी = $4।", "இணை $1 ↔ $2: நீலம் = $3, ஆரஞ்சு = $4."],
  [/^(\d+) OSM-only$/, "$1 केवल OSM में", "$1 OSM-இல் மட்டும்"],
  [/^local shift ([\d.]+)–([\d.]+) m, from (\d+) anchor buildings$/, "स्थानीय खिसकाव $1–$2 मी, $3 संदर्भ इमारतों से", "உள்ளூர் இடப்பெயர்ச்சி $1–$2 மீ, $3 நங்கூரக் கட்டடங்களிலிருந்து"],
  [/^OSM buildings; (\d+) confirmed by another source$/, "OSM इमारतें; $1 की दूसरे स्रोत से पुष्टि", "OSM கட்டடங்கள்; $1 மற்றொரு மூலத்தால் உறுதி"],
];

function t(s) {
  if (LANG === "en" || s == null) return s;
  const hit = T_MAP.get(s);
  if (hit) return hit[LANG] || s;
  for (const [re, hi, ta] of T_PATTERNS) if (re.test(s)) return s.replace(re, LANG === "hi" ? hi : ta);
  return s;
}

(function () {
  document.documentElement.lang = LANG;
  if (LANG === "en") return;
  const done = new WeakMap();      // text node -> the text we wrote, so we don't translate twice
  function tx(node) {
    const raw = node.nodeValue;
    if (!raw || done.get(node) === raw) return;
    const s = raw.trim().replace(/\s+/g, " ");
    if (!s || !/[A-Za-z]/.test(s)) return;
    const out = t(s);
    if (out !== s) { const v = raw.replace(raw.trim(), out); node.nodeValue = v; done.set(node, v); }
  }
  function walk(root) {
    if (root.nodeType === 3) { tx(root); return; }
    if (root.nodeType !== 1 || /^(SCRIPT|STYLE|TEXTAREA|CODE)$/.test(root.tagName) || root.closest?.(".leaflet-pane, .mono, code")) return;
    for (const a of ["placeholder", "title", "aria-label"]) {
      const v = root.getAttribute && root.getAttribute(a);
      if (v) { const o = t(v.trim()); if (o !== v.trim()) root.setAttribute(a, o); }
    }
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentElement && n.parentElement.closest("script, style, textarea, code, .mono, .leaflet-pane") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
    let n; while ((n = w.nextNode())) tx(n);
    root.querySelectorAll && root.querySelectorAll("[placeholder], [title], [aria-label]").forEach((e) => {
      for (const a of ["placeholder", "title", "aria-label"]) { const v = e.getAttribute(a); if (v) { const o = t(v.trim()); if (o !== v.trim()) e.setAttribute(a, o); } }
    });
  }
  const start = () => {
    walk(document.body);
    new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === "characterData") tx(m.target);
        else m.addedNodes.forEach(walk);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();

/* A small language menu; changing it reloads the page in that language. */
function langPicker(compact) {
  const s = document.createElement("select");
  s.className = "lang"; s.setAttribute("aria-label", "Language");
  for (const [code, name] of LANGS) { const o = document.createElement("option"); o.value = code; o.textContent = name; if (code === LANG) o.selected = true; s.append(o); }
  s.addEventListener("change", () => { try { localStorage.setItem("lang", s.value); } catch (e) { /* blocked */ } location.reload(); });
  if (compact) s.classList.add("compact");
  return s;
}
