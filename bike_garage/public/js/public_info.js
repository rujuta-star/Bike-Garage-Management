(() => {
	const page = document.querySelector(".bg-lovable-landing.info-page");
	if (!page) return;

	const translations = {
		"← Back to Home": ["← मुख्यपृष्ठावर परत जा", "← होम पर वापस जाएँ"],
		"Features": ["वैशिष्ट्ये", "विशेषताएँ"],
		"Benefits": ["फायदे", "फ़ायदे"],
		"How It Works": ["हे कसे कार्य करते", "यह कैसे काम करता है"],
		"Sign In": ["साइन इन करा", "साइन इन करें"],
		"Request Access": ["प्रवेशाची विनंती करा", "एक्सेस का अनुरोध करें"],
		"Contact Us": ["संपर्क करा", "संपर्क करें"],
		"Explore": ["पाहा", "देखें"],
		"Information": ["माहिती", "जानकारी"],
		"Privacy Policy": ["गोपनीयता धोरण", "गोपनीयता नीति"],
		"Terms of Service": ["सेवा अटी", "सेवा की शर्तें"],
		"Help / Support": ["मदत / सहाय्य", "मदद / सहायता"],
		"Help & Support": ["मदत आणि सहाय्य", "मदद और सहायता"],
		"Bike Garage Management. All rights reserved.": ["Bike Garage Management. सर्व हक्क राखीव.", "Bike Garage Management. सर्वाधिकार सुरक्षित."],
		"Management": ["व्यवस्थापन", "प्रबंधन"],
		"A workspace for independent motorcycle garages to manage customers, bikes, service jobs, parts and business records.": ["स्वतंत्र मोटरसायकल गॅरेजसाठी ग्राहक, दुचाकी, सर्व्हिसची कामे, सुटे भाग आणि व्यावसायिक नोंदी व्यवस्थापित करण्याचे वर्कस्पेस.", "स्वतंत्र मोटरसाइकिल गैराज के लिए ग्राहक, बाइक, सर्विस जॉब, पुर्ज़े और कारोबारी रिकॉर्ड संभालने का वर्कस्पेस."],
		"Language": ["भाषा", "भाषा"],
		"Switch to dark theme": ["डार्क थीमवर जा", "डार्क थीम पर जाएँ"],
		"Switch to light theme": ["लाइट थीमवर जा", "लाइट थीम पर जाएँ"],
		"Open menu": ["मेनू उघडा", "मेनू खोलें"],
		"Close menu": ["मेनू बंद करा", "मेनू बंद करें"],
		"Contact Us | Bike Garage": ["संपर्क करा | Bike Garage", "संपर्क करें | Bike Garage"],
		"Privacy Policy | Bike Garage": ["गोपनीयता धोरण | Bike Garage", "गोपनीयता नीति | Bike Garage"],
		"Terms of Service | Bike Garage": ["सेवा अटी | Bike Garage", "सेवा की शर्तें | Bike Garage"],
		"Help & Support | Bike Garage": ["मदत आणि सहाय्य | Bike Garage", "मदद और सहायता | Bike Garage"],
		"We're here to help": ["आम्ही मदतीसाठी येथे आहोत", "हम सहायता के लिए यहाँ हैं"],
		"Getting started": ["सुरुवात करा", "शुरू करें"],
		"Your information": ["तुमची माहिती", "आपकी जानकारी"],
		"Using Bike Garage": ["Bike Garage वापरणे", "Bike Garage का उपयोग"],
		"For help with Bike Garage, use the support route that applies to your request below.": ["Bike Garage साठी मदत हवी असल्यास, तुमच्या विनंतीनुसार खालील सहाय्याचा मार्ग वापरा.", "Bike Garage में मदद के लिए, अपने अनुरोध के अनुसार नीचे दिया गया सहायता तरीका अपनाएँ।"],
		"Support contact": ["सहाय्य संपर्क", "सहायता संपर्क"],
		"Email:": ["ईमेल:", "ईमेल:"],
		"and": ["आणि", "और"],
		"Phone:": ["फोन:", "फ़ोन:"],
		"WhatsApp:": ["WhatsApp:", "WhatsApp:"],
		"Message us on WhatsApp": ["WhatsApp वर संदेश पाठवा", "WhatsApp पर संदेश भेजें"],
		"To request support, email either address or contact us on WhatsApp with your garage name and a description of the issue. Do not include passwords, login links, or authentication codes. If you already use a garage workspace, you can also contact your garage administrator for account-access help.": ["सहाय्य मागण्यासाठी, तुमच्या गॅरेजचे नाव आणि समस्येचे वर्णन देऊन यापैकी कोणत्याही ईमेलवर किंवा WhatsApp वर संपर्क साधा. पासवर्ड, लॉगिन लिंक किंवा प्रमाणीकरण कोड पाठवू नका. तुम्ही आधीपासून गॅरेज वर्कस्पेस वापरत असल्यास, खाते प्रवेशासाठी तुमच्या गॅरेज प्रशासकाशी संपर्क साधू शकता.", "सहायता के लिए, अपने गैराज का नाम और समस्या का विवरण देकर इनमें से किसी ईमेल या WhatsApp पर संपर्क करें। पासवर्ड, लॉगिन लिंक या प्रमाणीकरण कोड न भेजें। यदि आप पहले से गैराज वर्कस्पेस का उपयोग करते हैं, तो खाते की पहुँच के लिए अपने गैराज व्यवस्थापक से भी संपर्क कर सकते हैं।"],
		"Requesting garage access": ["गॅरेज प्रवेशाची विनंती", "गैराज एक्सेस का अनुरोध"],
		"If you are applying for a new garage workspace, use the": ["नवीन गॅरेज वर्कस्पेससाठी अर्ज करत असल्यास,", "नए गैराज वर्कस्पेस के लिए आवेदन करने हेतु,"],
		". That form is for access applications, not general support requests.": [" वापरा। हा फॉर्म प्रवेश अर्जांसाठी आहे, सामान्य सहाय्य विनंतीसाठी नाही.", " इस्तेमाल करें। यह फ़ॉर्म एक्सेस आवेदन के लिए है, सामान्य सहायता अनुरोध के लिए नहीं।"],
		"Login assistance": ["लॉगिनसाठी मदत", "लॉगिन सहायता"],
		"Use the": ["येथे", "यहाँ"],
		"to log in or follow its password-recovery link.": ["लॉगिन करा किंवा पासवर्ड पुनर्प्राप्ती लिंक वापरा.", "लॉगिन करें या पासवर्ड रिकवरी लिंक का उपयोग करें।"],
		"Sign In page": ["साइन इन पृष्ठावर", "साइन इन पेज पर"],
		"Request Access form": ["प्रवेश विनंती फॉर्म", "एक्सेस अनुरोध फ़ॉर्म"],
		"Contact Us page": ["संपर्क पृष्ठावर", "संपर्क पेज पर"],
		"This page describes the information Bike Garage Management handles through the features currently implemented in this application. Hosting, retention, and contact details depend on the operator of the Frappe site running the app.": ["या अॅपमध्ये सध्या उपलब्ध असलेल्या वैशिष्ट्यांद्वारे Bike Garage Management कोणती माहिती हाताळते, हे या पृष्ठावर दिले आहे. होस्टिंग, माहिती किती काळ ठेवली जाते आणि संपर्काचे तपशील अॅप चालवणाऱ्या Frappe साइटच्या ऑपरेटरवर अवलंबून असतात.", "यह पेज बताता है कि इस ऐप में मौजूद सुविधाओं के माध्यम से Bike Garage Management कौन-सी जानकारी संभालता है। होस्टिंग, जानकारी रखने की अवधि और संपर्क विवरण इस ऐप को चलाने वाली Frappe साइट के ऑपरेटर पर निर्भर करते हैं।"],
		"Information collected": ["गोळा केलेली माहिती", "एकत्र की गई जानकारी"],
		"The public garage-access form asks for a garage name, owner name, email address, and phone number. Address, city, state, and PIN code are optional fields. Submitting the form saves a pending garage application; it does not create a login account or membership. The form checks whether the email already belongs to a user or garage application and avoids creating a duplicate.": ["सार्वजनिक गॅरेज प्रवेश फॉर्ममध्ये गॅरेजचे नाव, मालकाचे नाव, ईमेल पत्ता आणि फोन नंबर विचारला जातो. पत्ता, शहर, राज्य आणि पिन कोड ऐच्छिक आहेत. फॉर्म सबमिट केल्यावर गॅरेजचा प्रलंबित अर्ज जतन होतो; लॉगिन खाते किंवा सदस्यत्व तयार होत नाही. ईमेल आधीपासून वापरकर्त्याशी किंवा गॅरेज अर्जाशी जोडलेला आहे का हे फॉर्म तपासतो आणि दुबार अर्ज टाळतो.", "सार्वजनिक गैराज एक्सेस फ़ॉर्म में गैराज का नाम, मालिक का नाम, ईमेल पता और फ़ोन नंबर माँगा जाता है। पता, शहर, राज्य और पिन कोड वैकल्पिक हैं। फ़ॉर्म जमा करने पर गैराज का लंबित आवेदन सहेजा जाता है; इससे लॉगिन खाता या सदस्यता नहीं बनती। फ़ॉर्म जाँचता है कि ईमेल पहले से किसी उपयोगकर्ता या गैराज आवेदन से जुड़ा है या नहीं और दोहराया आवेदन रोकता है।"],
		"After approval, the owner can complete registration using the separate registration link. The application then creates the account and garage membership. Login and password recovery use Frappe's native account flow.": ["मंजुरीनंतर, मालक स्वतंत्र नोंदणी लिंकद्वारे नोंदणी पूर्ण करू शकतो. त्यानंतर अॅप खाते आणि गॅरेज सदस्यत्व तयार करते. लॉगिन आणि पासवर्ड पुनर्प्राप्तीसाठी Frappe ची मूळ खाते प्रक्रिया वापरली जाते.", "मंज़ूरी के बाद, मालिक अलग पंजीकरण लिंक से पंजीकरण पूरा कर सकता है। इसके बाद ऐप खाता और गैराज सदस्यता बनाता है। लॉगिन और पासवर्ड रिकवरी के लिए Frappe की मूल खाता प्रक्रिया इस्तेमाल होती है।"],
		"When a garage uses the workspace, its users may enter customer contact details, motorcycle and registration information, job-card and service records, spare-parts and stock records, sales and payment information, expenses, and related business records. The app also stores a signed-in user's language preference in their Frappe user record.": ["गॅरेज वर्कस्पेस वापरताना, वापरकर्ते ग्राहकांचे संपर्क तपशील, मोटरसायकल आणि नोंदणीची माहिती, जॉब कार्ड व सर्व्हिस नोंदी, सुटे भाग व साठ्याच्या नोंदी, विक्री व पेमेंटची माहिती, खर्च आणि संबंधित व्यावसायिक नोंदी भरू शकतात. अॅप लॉगिन केलेल्या वापरकर्त्याची भाषा पसंती त्यांच्या Frappe वापरकर्ता नोंदीत साठवते.", "गैराज वर्कस्पेस में उपयोगकर्ता ग्राहक संपर्क विवरण, मोटरसाइकिल और पंजीकरण जानकारी, जॉब कार्ड और सर्विस रिकॉर्ड, पुर्ज़ों और स्टॉक के रिकॉर्ड, बिक्री और भुगतान की जानकारी, खर्च और संबंधित कारोबारी रिकॉर्ड दर्ज कर सकते हैं। ऐप लॉगिन किए उपयोगकर्ता की भाषा पसंद को उनके Frappe उपयोगकर्ता रिकॉर्ड में भी सहेजता है।"],
		"How information is used": ["माहितीचा वापर कसा होतो", "जानकारी का उपयोग कैसे होता है"],
		"Access-request details are used for application review and, after approval, for owner registration. Workspace records support the garage-management features and are displayed to users according to their garage membership and application permissions. Platform administrators use application details to review and administer garage access.": ["प्रवेश विनंतीतील तपशील अर्ज तपासण्यासाठी आणि मंजुरीनंतर मालकाच्या नोंदणीसाठी वापरले जातात. वर्कस्पेसमधील नोंदी गॅरेज व्यवस्थापन वैशिष्ट्यांसाठी वापरल्या जातात आणि सदस्यत्व व अॅप परवानग्यांनुसार वापरकर्त्यांना दाखवल्या जातात. प्लॅटफॉर्म प्रशासक अर्ज तपशील वापरून गॅरेज प्रवेश तपासतात आणि व्यवस्थापित करतात.", "एक्सेस अनुरोध के विवरण आवेदन की समीक्षा और मंज़ूरी के बाद मालिक के पंजीकरण के लिए उपयोग किए जाते हैं। वर्कस्पेस रिकॉर्ड गैराज प्रबंधन सुविधाओं में काम आते हैं और सदस्यता तथा ऐप अनुमतियों के अनुसार उपयोगकर्ताओं को दिखाए जाते हैं। प्लेटफ़ॉर्म व्यवस्थापक आवेदन विवरण से गैराज एक्सेस की समीक्षा और व्यवस्था करते हैं।"],
		"Storage and protection": ["साठवण आणि संरक्षण", "संग्रहण और सुरक्षा"],
		"Application and workspace records are stored with the Frappe site database running this app. The application checks account authorization and garage-scoped access in its server-side routes and APIs. Frappe provides the login, session, password-recovery, and CSRF mechanisms used by the site. These controls do not guarantee that information is immune to every security risk.": ["अर्ज आणि वर्कस्पेस नोंदी हे अॅप चालवणाऱ्या Frappe साइटच्या डेटाबेसमध्ये साठवल्या जातात. अॅपच्या सर्व्हर-साइड रूट्स आणि API मध्ये खाते प्रमाणीकरण व गॅरेज-आधारित प्रवेश तपासला जातो. साइट लॉगिन, सत्र, पासवर्ड पुनर्प्राप्ती आणि CSRF साठी Frappe यंत्रणा वापरते. या नियंत्रणांमुळे प्रत्येक सुरक्षा जोखमीपासून संपूर्ण संरक्षणाची हमी मिळत नाही.", "आवेदन और वर्कस्पेस रिकॉर्ड इस ऐप को चलाने वाली Frappe साइट के डेटाबेस में सहेजे जाते हैं। ऐप के सर्वर-साइड रूट और API खाता प्राधिकरण तथा गैराज-आधारित एक्सेस जाँचते हैं। साइट लॉगिन, सत्र, पासवर्ड रिकवरी और CSRF के लिए Frappe की व्यवस्था इस्तेमाल करती है। ये नियंत्रण हर सुरक्षा जोखिम से पूर्ण सुरक्षा की गारंटी नहीं देते।"],
		"This app does not define a general automatic deletion schedule. Database hosting, backups, retention, and infrastructure safeguards are managed by the operator of the Frappe site; this application does not specify those arrangements.": ["हे अॅप सर्वसाधारण स्वयंचलित हटवण्याचे वेळापत्रक ठरवत नाही. डेटाबेस होस्टिंग, बॅकअप, माहिती साठवण्याचा कालावधी आणि पायाभूत सुरक्षा Frappe साइटचा ऑपरेटर व्यवस्थापित करतो; या अॅपमध्ये त्या व्यवस्थांचे तपशील निश्चित केलेले नाहीत.", "यह ऐप सामान्य स्वचालित हटाने की समय-सारणी तय नहीं करता। डेटाबेस होस्टिंग, बैकअप, जानकारी रखने की अवधि और बुनियादी सुरक्षा Frappe साइट का ऑपरेटर संभालता है; इस ऐप में इन व्यवस्थाओं का विवरण तय नहीं है।"],
		"Sharing and external requests": ["माहितीची देवाणघेवाण आणि बाह्य विनंत्या", "जानकारी साझा करना और बाहरी अनुरोध"],
		"An initial access request does not send an email. After an administrator approves an application, the app can queue an email containing a registration link if outgoing email is configured on the Frappe site. Email delivery is not guaranteed by the application.": ["प्रारंभिक प्रवेश विनंतीनंतर ईमेल पाठवला जात नाही. प्रशासकाने अर्ज मंजूर केल्यानंतर, Frappe साइटवर बाहेर जाणारे ईमेल कॉन्फिगर असल्यास अॅप नोंदणी लिंक असलेला ईमेल पाठवण्यासाठी रांगेत ठेवू शकते. ईमेल पोहोचण्याची हमी अॅप देत नाही.", "पहले एक्सेस अनुरोध पर ईमेल नहीं भेजा जाता। व्यवस्थापक द्वारा आवेदन मंज़ूर करने के बाद, Frappe साइट पर आउटगोइंग ईमेल कॉन्फ़िगर होने पर ऐप पंजीकरण लिंक वाला ईमेल भेजने के लिए कतार में रख सकता है। ऐप ईमेल पहुँचने की गारंटी नहीं देता।"],
		"The public pages load web fonts from Google Fonts. When those fonts are requested, the browser connects to Google's font domains and may share standard connection information with that service. No analytics or advertising integration is configured by this app's public homepage.": ["सार्वजनिक पृष्ठ Google Fonts मधून वेब फॉन्ट लोड करतात. हे फॉन्ट मागवल्यावर ब्राउझर Google च्या फॉन्ट डोमेनशी जोडला जातो आणि त्या सेवेसोबत नेहमीची कनेक्शन माहिती शेअर होऊ शकते. या अॅपच्या सार्वजनिक मुख्यपृष्ठावर विश्लेषण किंवा जाहिरात एकत्रीकरण कॉन्फिगर केलेले नाही.", "सार्वजनिक पेज Google Fonts से वेब फ़ॉन्ट लोड करते हैं। फ़ॉन्ट माँगे जाने पर ब्राउज़र Google के फ़ॉन्ट डोमेन से जुड़ता है और उस सेवा के साथ सामान्य कनेक्शन जानकारी साझा हो सकती है। इस ऐप के सार्वजनिक होमपेज पर विश्लेषण या विज्ञापन एकीकरण कॉन्फ़िगर नहीं है।"],
		"Garage records are available to authorized users for their garage and to administrators as permitted by the app and site configuration. The operator should publish any additional hosting-provider or service-provider disclosures that apply to their deployment.": ["अॅप आणि साइट कॉन्फिगरेशननुसार गॅरेजच्या अधिकृत वापरकर्त्यांना त्यांच्या गॅरेजच्या नोंदी आणि प्रशासकांना परवानगी असलेल्या नोंदी उपलब्ध असतात. त्यांच्या वापरात लागू होणाऱ्या होस्टिंग किंवा सेवा पुरवठादारांविषयीची अतिरिक्त माहिती ऑपरेटरने प्रकाशित करावी.", "ऐप और साइट कॉन्फ़िगरेशन के अनुसार अधिकृत उपयोगकर्ताओं को अपने गैराज के रिकॉर्ड और व्यवस्थापकों को अनुमत रिकॉर्ड उपलब्ध होते हैं। लागू होस्टिंग या सेवा प्रदाता संबंधी अतिरिक्त जानकारी ऑपरेटर को प्रकाशित करनी चाहिए।"],
		"Questions or data requests": ["प्रश्न किंवा माहितीविषयक विनंत्या", "प्रश्न या जानकारी के अनुरोध"],
		"For a privacy question or data request, contact your garage administrator or use the application contact email listed on the": ["गोपनीयतेविषयी प्रश्न किंवा माहितीची विनंती असल्यास, तुमच्या गॅरेज प्रशासकाशी संपर्क साधा किंवा", "गोपनीयता संबंधी प्रश्न या जानकारी के अनुरोध के लिए अपने गैराज व्यवस्थापक से संपर्क करें या"],
		". A separate privacy-request workflow is not configured in the application.": ["। गोपनीयता विनंत्यांसाठी स्वतंत्र प्रक्रिया अॅपमध्ये कॉन्फिगर केलेली नाही.", "। ऐप में गोपनीयता अनुरोध के लिए अलग प्रक्रिया कॉन्फ़िगर नहीं है।"],
		"These terms explain the expected use of Bike Garage Management as provided by the operator of the Frappe site. They are service information, not legal advice; the site operator should review them for the specific service they offer.": ["Frappe साइटच्या ऑपरेटरद्वारे दिलेल्या Bike Garage Management चा अपेक्षित वापर या अटी स्पष्ट करतात. ही सेवा-विषयक माहिती आहे, कायदेशीर सल्ला नाही; साइट ऑपरेटरने त्यांच्या विशिष्ट सेवेसाठी या अटींचे पुनरावलोकन करावे.", "ये शर्तें Frappe साइट के ऑपरेटर द्वारा उपलब्ध Bike Garage Management के अपेक्षित उपयोग को समझाती हैं। यह सेवा संबंधी जानकारी है, कानूनी सलाह नहीं; साइट ऑपरेटर अपनी विशिष्ट सेवा के अनुसार इनकी समीक्षा करें।"],
		"Account registration and approval": ["खाते नोंदणी आणि मंजुरी", "खाता पंजीकरण और मंज़ूरी"],
		"A garage owner may request access through the public form. Submitting a request creates a pending application, not a user account or a promise of access. An administrator reviews the request. If it is approved and outgoing email is configured, the owner may receive a separate, time-limited registration link to create the account. Access to a garage workspace depends on an active account and garage membership.": ["गॅरेज मालक सार्वजनिक फॉर्मद्वारे प्रवेशाची विनंती करू शकतो. विनंती सबमिट केल्याने प्रलंबित अर्ज तयार होतो; वापरकर्ता खाते किंवा प्रवेशाचे आश्वासन मिळत नाही. प्रशासक विनंती तपासतो. मंजुरीनंतर आणि बाहेर जाणारे ईमेल कॉन्फिगर असल्यास, खाते तयार करण्यासाठी मालकाला स्वतंत्र, मर्यादित कालावधीची नोंदणी लिंक मिळू शकते. गॅरेज वर्कस्पेससाठी सक्रिय खाते आणि गॅरेज सदस्यत्व आवश्यक आहे.", "गैराज मालिक सार्वजनिक फ़ॉर्म से एक्सेस माँग सकता है। अनुरोध जमा करने से लंबित आवेदन बनता है, उपयोगकर्ता खाता या एक्सेस का वादा नहीं। व्यवस्थापक अनुरोध की समीक्षा करता है। मंज़ूरी के बाद और आउटगोइंग ईमेल कॉन्फ़िगर होने पर, खाता बनाने के लिए मालिक को अलग, सीमित अवधि वाला पंजीकरण लिंक मिल सकता है। गैराज वर्कस्पेस के लिए सक्रिय खाता और गैराज सदस्यता आवश्यक है।"],
		"Account responsibilities": ["खात्याच्या जबाबदाऱ्या", "खाते की ज़िम्मेदारियाँ"],
		"Users are responsible for providing accurate access-request and account information, keeping their sign-in credentials private, and using their own account. Contact the garage administrator if access appears incorrect or should be changed. Do not share another person's credentials.": ["प्रवेश विनंती आणि खाते माहिती अचूक देणे, लॉगिन तपशील गोपनीय ठेवणे आणि स्वतःचे खाते वापरणे ही वापरकर्त्यांची जबाबदारी आहे. प्रवेश चुकीचा वाटल्यास किंवा बदलायचा असल्यास गॅरेज प्रशासकाशी संपर्क साधा. दुसऱ्या व्यक्तीचे लॉगिन तपशील शेअर करू नका.", "सही एक्सेस अनुरोध और खाता जानकारी देना, लॉगिन विवरण गोपनीय रखना और अपना खाता इस्तेमाल करना उपयोगकर्ताओं की ज़िम्मेदारी है। एक्सेस गलत लगे या बदलना हो तो गैराज व्यवस्थापक से संपर्क करें। किसी अन्य व्यक्ति के लॉगिन विवरण साझा न करें।"],
		"Acceptable use": ["स्वीकार्य वापर", "स्वीकार्य उपयोग"],
		"Use the application for legitimate garage-management work and only with the records you are authorized to access. Do not attempt to access another garage's information, bypass permissions, disrupt the service, or submit information you are not authorized to provide.": ["अॅपचा वापर वैध गॅरेज व्यवस्थापनासाठी आणि तुम्हाला प्रवेशाची परवानगी असलेल्या नोंदींसाठीच करा. दुसऱ्या गॅरेजची माहिती मिळवण्याचा, परवानग्या टाळण्याचा, सेवा विस्कळीत करण्याचा किंवा देण्याचा अधिकार नसलेली माहिती सबमिट करण्याचा प्रयत्न करू नका.", "ऐप का उपयोग वैध गैराज प्रबंधन कार्य और केवल उन रिकॉर्ड के लिए करें जिन्हें देखने की आपको अनुमति है। किसी अन्य गैराज की जानकारी पाने, अनुमतियाँ दरकिनार करने, सेवा बाधित करने या ऐसी जानकारी जमा करने का प्रयास न करें जिसे देने का अधिकार आपको नहीं है।"],
		"Service availability": ["सेवा उपलब्धता", "सेवा की उपलब्धता"],
		"The application is provided through the Frappe site operated for your deployment. The site may be unavailable, changed, or discontinued by its operator. The app does not promise continuous availability or that every feature will always be error-free.": ["तुमच्या वापरासाठी चालवलेल्या Frappe साइटद्वारे अॅप उपलब्ध आहे. साइट ऑपरेटरकडून ती अनुपलब्ध, बदललेली किंवा बंद केली जाऊ शकते. सतत उपलब्धता किंवा प्रत्येक वैशिष्ट्य नेहमी त्रुटीविरहित राहण्याचे आश्वासन अॅप देत नाही.", "आपके उपयोग के लिए संचालित Frappe साइट के माध्यम से ऐप उपलब्ध है। साइट ऑपरेटर इसे अनुपलब्ध, बदल या बंद कर सकता है। ऐप निरंतर उपलब्धता या हर सुविधा के हमेशा त्रुटिरहित रहने का वादा नहीं करता।"],
		"Records and limitations": ["नोंदी आणि मर्यादा", "रिकॉर्ड और सीमाएँ"],
		"Bike Garage provides tools for recording and reviewing business information. Users remain responsible for checking their records and decisions and for meeting any requirements that apply to their business. Reports and screens should not be treated as professional, tax, accounting, or legal advice.": ["व्यावसायिक माहिती नोंदवण्यासाठी आणि तपासण्यासाठी Bike Garage साधने देते. स्वतःच्या नोंदी व निर्णय तपासणे आणि व्यवसायाला लागू असलेल्या आवश्यकता पूर्ण करणे ही वापरकर्त्यांची जबाबदारी आहे. अहवाल आणि स्क्रीनना व्यावसायिक, कर, लेखा किंवा कायदेशीर सल्ला समजू नये.", "व्यावसायिक जानकारी दर्ज करने और देखने के लिए Bike Garage उपकरण देता है। अपने रिकॉर्ड और निर्णय जाँचना तथा कारोबार पर लागू आवश्यकताएँ पूरी करना उपयोगकर्ताओं की ज़िम्मेदारी है। रिपोर्ट और स्क्रीन को पेशेवर, कर, लेखा या कानूनी सलाह न मानें।"],
		"For account help or site-specific service questions, see": ["खाते किंवा साइट-विशिष्ट सेवा प्रश्नांसाठी", "खाते या साइट-विशिष्ट सेवा प्रश्नों के लिए"],
		"or": ["किंवा", "या"],
		".": ["।", "।"],
		"Help / Support | Bike Garage": ["मदत / सहाय्य | Bike Garage", "मदद / सहायता | Bike Garage"],
		"Follow the steps below to request a garage workspace, set up your account, and sign in.": ["गॅरेज वर्कस्पेसची विनंती, खाते सेटअप आणि लॉगिनसाठी खालील पायऱ्या पाळा.", "गैराज वर्कस्पेस माँगने, खाता सेटअप और लॉगिन के लिए नीचे दिए चरण अपनाएँ।"],
		"1. Request garage access": ["१. गॅरेज प्रवेशाची विनंती करा", "१. गैराज एक्सेस का अनुरोध करें"],
		"While signed out, open the": ["लॉगआउट असताना,", "लॉगआउट रहते हुए,"],
		"and enter the garage name, owner's name, work email, and phone number. Address, city, state, and PIN code are optional. Submitting the form creates a pending application only; it does not create an account or membership. The form displays a generic acknowledgement and does not send an email at this stage.": ["उघडा आणि गॅरेजचे नाव, मालकाचे नाव, कामाचा ईमेल आणि फोन नंबर भरा. पत्ता, शहर, राज्य आणि पिन कोड ऐच्छिक आहेत. फॉर्म सबमिट केल्याने फक्त प्रलंबित अर्ज तयार होतो; खाते किंवा सदस्यत्व तयार होत नाही. फॉर्म सामान्य पुष्टी दाखवतो आणि या टप्प्यावर ईमेल पाठवत नाही.", "खोलें और गैराज का नाम, मालिक का नाम, कार्य ईमेल और फ़ोन नंबर भरें। पता, शहर, राज्य और पिन कोड वैकल्पिक हैं। फ़ॉर्म जमा करने से केवल लंबित आवेदन बनता है; खाता या सदस्यता नहीं। फ़ॉर्म सामान्य पुष्टि दिखाता है और इस चरण पर ईमेल नहीं भेजता।"],
		"2. Wait for administrator review": ["२. प्रशासकाच्या तपासणीची प्रतीक्षा करा", "२. व्यवस्थापक की समीक्षा की प्रतीक्षा करें"],
		"A Bike Garage administrator reviews the application. Until it is approved and registration is completed, there is no garage owner login created by the request form. If you already have an account, a new access request for that same email will not create a duplicate application.": ["Bike Garage प्रशासक अर्ज तपासतो. अर्ज मंजूर होऊन नोंदणी पूर्ण होईपर्यंत विनंती फॉर्मद्वारे गॅरेज मालकाचे लॉगिन तयार होत नाही. तुमचे खाते आधीच असल्यास, त्याच ईमेलसाठी केलेली नवीन प्रवेश विनंती दुबार अर्ज तयार करणार नाही.", "Bike Garage व्यवस्थापक आवेदन की समीक्षा करता है। आवेदन मंज़ूर होकर पंजीकरण पूरा होने तक अनुरोध फ़ॉर्म से गैराज मालिक का लॉगिन नहीं बनता। यदि आपका खाता पहले से है, तो उसी ईमेल से नया एक्सेस अनुरोध दोहराया आवेदन नहीं बनाएगा।"],
		"3. Complete account setup": ["३. खाते सेटअप पूर्ण करा", "३. खाता सेटअप पूरा करें"],
		"After approval, the administrator can send a separate registration link to the email on the application when outgoing email is configured. The link expires after 48 hours. Follow it to set a password and complete owner registration. If no email arrives, contact your garage administrator using their existing support channel.": ["मंजुरीनंतर, बाहेर जाणारे ईमेल कॉन्फिगर असल्यास प्रशासक अर्जातील ईमेलवर स्वतंत्र नोंदणी लिंक पाठवू शकतो. ही लिंक ४८ तासांनी कालबाह्य होते. लिंक उघडून पासवर्ड सेट करा आणि मालकाची नोंदणी पूर्ण करा. ईमेल न आल्यास, प्रशासकाशी त्यांच्या विद्यमान सहाय्य माध्यमातून संपर्क साधा.", "मंज़ूरी के बाद, आउटगोइंग ईमेल कॉन्फ़िगर होने पर व्यवस्थापक आवेदन वाले ईमेल पर अलग पंजीकरण लिंक भेज सकता है। लिंक ४८ घंटे में समाप्त हो जाती है। इसे खोलकर पासवर्ड सेट करें और मालिक का पंजीकरण पूरा करें। ईमेल न मिले तो व्यवस्थापक के मौजूदा सहायता माध्यम से संपर्क करें।"],
		"4. Sign in and open your workspace": ["४. साइन इन करून वर्कस्पेस उघडा", "४. साइन इन करके वर्कस्पेस खोलें"],
		"Go to": ["येथे जा:", "यहाँ जाएँ:"],
		"and use the account credentials you created. The workspace is available when the account has a valid active garage membership. Your permitted destination is selected by the application after authentication.": ["आणि तयार केलेले खाते तपशील वापरा. खात्याला वैध सक्रिय गॅरेज सदस्यत्व असल्यास वर्कस्पेस उपलब्ध होईल. प्रमाणीकरणानंतर अॅप तुमच्यासाठी परवानगीचे पृष्ठ निवडते.", "और बनाए गए खाते के विवरण इस्तेमाल करें। खाते में वैध सक्रिय गैराज सदस्यता होने पर वर्कस्पेस उपलब्ध होगा। प्रमाणीकरण के बाद ऐप आपके लिए अनुमत पेज चुनता है।"],
		"Password recovery": ["पासवर्ड पुनर्प्राप्ती", "पासवर्ड रिकवरी"],
		"Use the password-recovery link on the native Frappe login page and follow its instructions. If you cannot access the email on your account, ask your garage administrator for help.": ["Frappe लॉगिन पृष्ठावरील पासवर्ड पुनर्प्राप्ती लिंक वापरून सूचना पाळा. खात्यातील ईमेल वापरता येत नसल्यास, गॅरेज प्रशासकाची मदत घ्या.", "Frappe लॉगिन पेज पर पासवर्ड रिकवरी लिंक इस्तेमाल करके निर्देशों का पालन करें। खाते का ईमेल उपलब्ध न हो तो गैराज व्यवस्थापक से मदद लें।"],
		"Contact support": ["सहाय्याशी संपर्क साधा", "सहायता से संपर्क करें"],
		"For workspace access or garage-specific questions, contact your garage administrator. You can also email the application contact listed on the": ["वर्कस्पेस प्रवेश किंवा गॅरेजविषयक प्रश्नांसाठी, गॅरेज प्रशासकाशी संपर्क साधा. तसेच", "वर्कस्पेस एक्सेस या गैराज संबंधी प्रश्नों के लिए अपने गैराज व्यवस्थापक से संपर्क करें। आप"],
		"with your garage name and a description; do not include your password or authentication codes.": ["दिलेल्या अॅप संपर्काला गॅरेजचे नाव आणि वर्णनासह ईमेल करू शकता; पासवर्ड किंवा प्रमाणीकरण कोड पाठवू नका.", "दिए गए ऐप संपर्क को गैराज का नाम और विवरण ईमेल कर सकते हैं; पासवर्ड या प्रमाणीकरण कोड न भेजें।"],
	};

	const themeButton = page.querySelector("#themeBtn");
	const languageSelect = page.querySelector("#langSel");
	const originalTitle = document.title;
	const savedTheme = (() => {
		try {
			return window.localStorage.getItem("bg-theme");
		} catch (_error) {
			return null;
		}
	})();
	const initialTheme = savedTheme === "dark" || savedTheme === "light"
		? savedTheme
		: (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");

	const setTheme = (theme) => {
		page.setAttribute("data-theme", theme);
		const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
		themeButton?.setAttribute("aria-label", languageIndex < 0 ? label : translations[label][languageIndex]);
		try {
			window.localStorage.setItem("bg-theme", theme);
		} catch (_error) {
			// Theme changes still apply for this page when storage is unavailable.
		}
	};

	const textNodes = [];
	const collectTextNodes = (node) => {
		for (const child of node.childNodes) {
			if (child.nodeType === 3) {
				const key = child.nodeValue.trim();
				if (translations[key]) textNodes.push({node: child, key, raw: child.nodeValue});
			} else if (child.nodeType === 1 && !/^(SCRIPT|STYLE|SELECT)$/.test(child.tagName)) {
				collectTextNodes(child);
			}
		}
	};
	collectTextNodes(page);

	let languageIndex = 0;
	const setLanguage = (language) => {
		const index = language === "mr" ? 0 : language === "hi" ? 1 : -1;
		languageIndex = index;
		for (const {node, key, raw} of textNodes) {
			const translation = index < 0 ? key : translations[key][index];
			const start = raw.indexOf(key);
			node.nodeValue = raw.slice(0, start) + translation + raw.slice(start + key.length);
		}
		page.setAttribute("lang", language);
		if (languageSelect) languageSelect.value = language;
		if (themeButton) {
			const label = page.getAttribute("data-theme") === "dark" ? "Switch to light theme" : "Switch to dark theme";
			themeButton.setAttribute("aria-label", index < 0 ? label : translations[label][index]);
		}
		languageSelect?.setAttribute("aria-label", index < 0 ? "Language" : translations.Language[index]);
		const menuButton = page.querySelector("#menuBtn");
		const menuLabel = menuButton?.getAttribute("aria-expanded") === "true" ? "Close menu" : "Open menu";
		menuButton?.setAttribute("aria-label", index < 0 ? menuLabel : translations[menuLabel][index]);
		if (translations[originalTitle]) {
			document.title = index < 0 ? originalTitle : translations[originalTitle][index];
		}
		try {
			window.localStorage.setItem("bg-lang", language);
		} catch (_error) {
			// The selected language still applies to this page when storage is unavailable.
		}
	};

	setTheme(initialTheme);
	themeButton?.addEventListener("click", () => {
		setTheme(page.getAttribute("data-theme") === "dark" ? "light" : "dark");
	});
	languageSelect?.addEventListener("change", () => setLanguage(languageSelect.value));
	let initialLanguage = "en";
	try {
		initialLanguage = window.localStorage.getItem("bg-lang") || "en";
	} catch (_error) {
		initialLanguage = "en";
	}
	if (!["en", "mr", "hi"].includes(initialLanguage)) initialLanguage = "en";
	setLanguage(initialLanguage);

	const menuButton = page.querySelector("#menuBtn");
	const menu = page.querySelector("#mobileMenu");
	const setMenu = (open) => {
		menu?.classList.toggle("open", open);
		menuButton?.setAttribute("aria-expanded", String(open));
		const label = open ? "Close menu" : "Open menu";
		menuButton?.setAttribute("aria-label", languageIndex < 0 ? label : translations[label][languageIndex]);
	};
	menuButton?.addEventListener("click", () => {
		setMenu(!menu?.classList.contains("open"));
	});
	menu?.querySelectorAll("a").forEach((link) => {
		link.addEventListener("click", () => setMenu(false));
	});
	const year = page.querySelector("#year");
	if (year) year.textContent = new Date().getFullYear();
})();
