import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  Phone, 
  ChevronRight, 
  Bell, 
  Folder, 
  Check, 
  Clock, 
  Send, 
  Shield, 
  Cpu, 
  Building, 
  FileText, 
  AlertTriangle, 
  Download, 
  Printer, 
  Plus, 
  RotateCcw,
  ChevronLeft,
  BookOpen,
  Lock,
  Edit2,
  Trash2,
  CheckCircle2,
  Mic,
  Square
} from 'lucide-react';

const API_BASE = `http://${window.location.hostname}:8000`;

export default function App() {
  // Config & catalog data from backend
  const [config, setConfig] = useState({
    categories: [],
    subcategories: [],
    national_resources: [],
    threat_intelligence: [],
    evidence_by_category: {},
    generic_evidence: [],
  });

  // Session State
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hello. I'm here to help. Please describe what happened in your own words.",
      type: 'text'
    }
  ]);
  const [stage, setStage] = useState('stage_1_intake');
  const [classification, setClassification] = useState(null);
  const [summary, setSummary] = useState('');
  const [timeline, setTimeline] = useState([]);
  const [evidence, setEvidence] = useState({});
  const [followupAnswers, setFollowupAnswers] = useState({});
  const [remainingQuestions, setRemainingQuestions] = useState([]);
  const [summaryGenerated, setSummaryGenerated] = useState(false);

  // Playbook Content
  const [playbook, setPlaybook] = useState(null);
  const [expandedPlaybookSections, setExpandedPlaybookSections] = useState({});

  // Scam carousel index
  const [scamIndex, setScamIndex] = useState(0);

  // UI Local States
  const [userInput, setUserInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [editingSummary, setEditingSummary] = useState(false);
  const [editedSummaryText, setEditedSummaryText] = useState('');

  // Speech Recording States & Refs
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Refs for auto-scroll
  const messagesEndRef = useRef(null);

  useEffect(() => {
    // Scroll chat to bottom
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load config on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/config`)
      .then(res => {
        if (!res.ok) throw new Error("Failed to load config");
        return res.json();
      })
      .then(data => {
        if (data) {
          setConfig({
            categories: data.categories || [],
            subcategories: data.subcategories || [],
            national_resources: data.national_resources || [],
            threat_intelligence: data.threat_intelligence || [],
            evidence_by_category: data.evidence_by_category || {},
            generic_evidence: data.generic_evidence || [],
          });
        }
      })
      .catch(err => console.error("Error loading config:", err));
  }, []);

  // Load playbook when classification changes
  useEffect(() => {
    if (classification && classification.subcategory_id) {
      fetch(`${API_BASE}/api/playbook/${classification.subcategory_id}`)
        .then(res => res.json())
        .then(data => {
          setPlaybook(data);
          // Auto expand first section if available
          if (data.available && data.sections) {
            const keys = Object.keys(data.sections);
            if (keys.length > 0) {
              setExpandedPlaybookSections({ [keys[0]]: true });
            }
          }
        })
        .catch(err => console.error("Error loading playbook:", err));
    } else {
      setPlaybook(null);
      setExpandedPlaybookSections({});
    }
  }, [classification]);

  const resetSession = () => {
    setMessages([
      {
        role: 'assistant',
        content: "Hello. I'm here to help. Please describe what happened in your own words.",
        type: 'text'
      }
    ]);
    setStage('stage_1_intake');
    setClassification(null);
    setSummary('');
    setTimeline([]);
    setEvidence({});
    setFollowupAnswers({});
    setRemainingQuestions([]);
    setSummaryGenerated(false);
    setPlaybook(null);
    setExpandedPlaybookSections({});
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      
      let recorder;
      if (MediaRecorder.isTypeSupported('audio/webm')) {
        recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        recorder = new MediaRecorder(stream, { mimeType: 'audio/mp4' });
      } else {
        recorder = new MediaRecorder(stream);
      }
      
      mediaRecorderRef.current = recorder;
      
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
        stream.getTracks().forEach(track => track.stop());
        await uploadAudio(audioBlob);
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      alert("Could not access microphone. Please check permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const uploadAudio = async (blob) => {
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      const extension = blob.type.includes('mp4') ? 'm4a' : 'webm';
      formData.append('file', blob, `audio.${extension}`);

      const response = await fetch(`${API_BASE}/api/transcribe`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Transcription failed');
      }

      const data = await response.json();
      if (data.text) {
        setUserInput(prev => prev ? `${prev} ${data.text.trim()}` : data.text.trim());
      }
    } catch (err) {
      console.error("Error transcribing audio:", err);
      alert("Error transcribing audio. Please try again.");
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleSendMessage = async (textToSend) => {
    if (!textToSend.trim()) return;

    setIsChatLoading(true);
    // Add user message to state
    const newMessages = [...messages, { role: 'user', content: textToSend, type: 'text' }];
    setMessages(newMessages);
    setUserInput('');

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages.slice(0, -1), // Send previous messages
          stage,
          classification,
          followup_answers: followupAnswers,
          remaining_questions: remainingQuestions,
          evidence,
          user_input: textToSend,
          summary,
          timeline,
        })
      });

      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }

      const data = await res.json();
      if (data && data.messages) {
        setMessages(data.messages);
        setStage(data.stage || 'stage_1_intake');
        setClassification(data.classification || null);
        setFollowupAnswers(data.followup_answers || {});
        setRemainingQuestions(data.remaining_questions || []);

        if (data.summary !== undefined) {
          setSummary(data.summary || '');
          setEditedSummaryText(data.summary || '');
        }
        if (data.timeline !== undefined) {
          setTimeline(data.timeline || []);
        }
        if (data.evidence !== undefined) {
          setEvidence(data.evidence || {});
        }

        if (data.summary_generated) {
          setSummaryGenerated(true);
        }
      }
    } catch (err) {
      console.error("Chat error:", err);
    } finally {
      setIsChatLoading(false);
    }
  };

  // Handle classification override selection
  const handleClassificationOverride = async (subcatId) => {
    if (!subcatId) return;

    setIsChatLoading(true);
    try {
      const selectedSub = config.subcategories.find(s => s.id === subcatId);
      if (!selectedSub) return;
      const selectedCat = config.categories.find(c => c.id === selectedSub.category_id);
      if (!selectedCat) return;
      
      const newClassification = {
        category_id: selectedSub.category_id,
        category_name: selectedCat.name,
        subcategory_id: selectedSub.id,
        subcategory_name: selectedSub.name,
        match_confidence: 1.0,
        needs_confirmation: false,
      };
      setClassification(newClassification);
      setStage('stage_3_followup');

      // Fetch followup questions
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages,
          stage: 'stage_2_confirming',
          classification: newClassification,
          followup_answers: followupAnswers,
          remaining_questions: [],
          evidence,
          user_input: selectedSub.name, // Simulate confirming
          summary,
          timeline,
        })
      });

      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }

      const data = await res.json();
      if (data && data.messages) {
        setMessages(data.messages);
        setStage(data.stage || 'stage_1_intake');
        setClassification(data.classification || null);
        setFollowupAnswers(data.followup_answers || {});
        setRemainingQuestions(data.remaining_questions || []);

        if (data.summary !== undefined) {
          setSummary(data.summary || '');
          setEditedSummaryText(data.summary || '');
        }
        if (data.timeline !== undefined) {
          setTimeline(data.timeline || []);
        }
        if (data.evidence !== undefined) {
          setEvidence(data.evidence || {});
        }

        if (data.summary_generated) {
          setSummaryGenerated(true);
        }
      }
    } catch (err) {
      console.error("Override error:", err);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleToggleEvidence = (itemId) => {
    const updated = { ...evidence, [itemId]: !evidence[itemId] };
    setEvidence(updated);
  };

  const handleRegenerateSummary = async () => {
    if (!classification) return;
    setIsSummaryLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/generate-summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incident_description: messages[1]?.content || '',
          classification,
          followup_answers: followupAnswers,
          evidence,
        })
      });
      const data = await res.json();
      setSummary(data.summary);
      setEditedSummaryText(data.summary);
      setTimeline(data.timeline || []);
      setSummaryGenerated(true);
    } catch (err) {
      console.error("Regenerate summary error:", err);
    } finally {
      setIsSummaryLoading(false);
    }
  };

  // Export handlers
  const handleExport = async (format) => {
    const caseDataPackage = {
      incident_description: messages[1]?.content || '',
      classification,
      summary,
      timeline,
      evidence,
      followup_answers: followupAnswers,
      evidence_labels: getEvidenceLabelsMap(),
    };

    try {
      const response = await fetch(`${API_BASE}/api/export/${format}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(caseDataPackage)
      });
      
      if (format === 'html') {
        const html = await response.text();
        const win = window.open();
        win.document.write(html);
        win.document.close();
      } else {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = format === 'pdf' ? 'CFRO_FIR.pdf' : format === 'txt' ? 'CFRO_Complaint.txt' : 'CFRO_Report.md';
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
    } catch (err) {
      console.error(`Export ${format} failed:`, err);
    }
  };

  const getEvidenceItemsList = () => {
    if (!classification) return [];
    const catId = classification.category_id;
    const items = config.evidence_by_category[catId] || config.evidence_by_category['other-categories'] || [];
    return [...items, ...config.generic_evidence];
  };

  const getEvidenceLabelsMap = () => {
    const map = {};
    getEvidenceItemsList().forEach(it => {
      map[it.id] = it.label;
    });
    return map;
  };

  // Timeline helpers
  const handleTimelineChange = (idx, field, val) => {
    const updated = [...timeline];
    updated[idx] = { ...updated[idx], [field]: val };
    setTimeline(updated);
  };

  const handleAddTimelineRow = () => {
    setTimeline([...timeline, { time: 'Approx Date/Time', event: 'New event description' }]);
  };

  const handleRemoveTimelineRow = (idx) => {
    setTimeline(timeline.filter((_, i) => i !== idx));
  };

  // Render elements
  const categoryId = classification?.category_id;
  const subcategoryName = classification?.subcategory_name || 'Unclassified Incident';
  const categoryName = classification?.category_name || 'Other';
  const confidenceScore = classification?.match_confidence || 0.0;
  const needsConfirmation = classification?.needs_confirmation;

  // Compile Emergency Actions list based on classification
  const getEmergencyActions = () => {
    if (categoryId === "online-financial-fraud") {
      return [
        { badge: "1930", color: "bg-red-500", title: "GOLDEN HOUR", desc: "Call the financial fraud helpline at 1930 immediately to freeze funds." },
        { badge: "BANK", color: "bg-blue-500", title: "BLOCK CREDENTIALS", desc: "Contact bank branch to freeze cards, net banking, and UPI IDs." },
        { badge: "STOP", color: "bg-orange-500", title: "STOP TRANSFERS", desc: "Do not send processing fees or security deposits to recover money." },
        { badge: "SAVE", color: "bg-green-500", title: "PRESERVE DETAILS", desc: "Save screenshots of UPI transaction IDs (UTR) and recipient bank names." }
      ];
    } else if (categoryId === "online-social-media") {
      return [
        { badge: "BLOCK", color: "bg-red-500", title: "REPORT & BLOCK", desc: "Use the social platform's internal reporting tools to flag offending profiles." },
        { badge: "ALERT", color: "bg-blue-500", title: "WARN NETWORK", desc: "Alert friends, family, and contacts that a fake account is impersonating you." },
        { badge: "SAVE", color: "bg-orange-500", title: "LOG EVIDENCE", desc: "Take screenshots of chats, comments, profile URLs, and timestamps." },
        { badge: "2FA", color: "bg-green-500", title: "SECURE ACCESS", desc: "Change account credentials and enable 2-Factor Authentication immediately." }
      ];
    } else if (categoryId === "hacking-damage-computer") {
      return [
        { badge: "OFF", color: "bg-red-500", title: "GO OFFLINE", desc: "Disconnect the compromised system from the network/Wi-Fi immediately." },
        { badge: "KEYS", color: "bg-blue-500", title: "CHANGE PASSWORDS", desc: "Update credentials of your bank, mail, and accounts from a clean device." },
        { badge: "LOGS", color: "bg-orange-500", title: "KEEP SYSTEM STATE", desc: "Do not run cleaner programs or format the system; keep files intact." },
        { badge: "BACK", color: "bg-green-500", title: "CHECK BACKUPS", desc: "Assess the date and status of the latest offline restore backups." }
      ];
    } else {
      return [
        { badge: "1930", color: "bg-red-500", title: "REPORT FRAUD", desc: "Call the national helpline at 1930 immediately to freeze financial losses." },
        { badge: "NET", color: "bg-blue-500", title: "GO OFFLINE", desc: "Disconnect compromised systems or mobile phones from Wi-Fi / Mobile Data." },
        { badge: "KEEP", color: "bg-orange-500", title: "DON'T DELETE", desc: "Preserve all communication logs, chats, SMS alert texts, and transaction screens." },
        { badge: "SAFE", color: "bg-green-500", title: "NEVER SHARE", desc: "Never share passwords, bank OTPs, or click on files received from unknown actors." }
      ];
    }
  };

  // Compile split evidence lists
  const evidenceItemsList = getEvidenceItemsList();
  const validatedEvidence = evidenceItemsList.filter(it => evidence[it.id]);
  const missingEvidence = evidenceItemsList.filter(it => !evidence[it.id]);

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-[#F0F2F5]">
      
      {/* ── TOP HEADER BAR ── */}
      <div className="bg-white px-6 py-3 border-b border-gray-200 shadow-sm flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#0B3C5D] rounded-lg text-yellow-400 flex items-center justify-center">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="text-md font-bold text-gray-900 leading-tight">Cyber Incident Response Assistant</div>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
              AI-Powered Cybercrime Incident Response &nbsp;·&nbsp; India &nbsp;·&nbsp; 1930 Helpline Active
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-green-50 border border-green-200 rounded-full text-xs font-semibold text-green-700">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            AI Active
          </div>

          <button 
            onClick={resetSession}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0B3C5D] hover:bg-[#082d47] text-white text-xs font-bold rounded-lg transition-all shadow-md shadow-blue-500/10"
          >
            <Plus className="w-3.5 h-3.5" />
            New Case
          </button>
          
          <button 
            onClick={resetSession}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 border border-gray-300 text-gray-700 text-xs font-bold rounded-lg transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
        </div>
      </div>

      {/* ── MAIN WORKSPACE ── */}
      <div className="flex-1 flex overflow-hidden p-4 gap-4">

        {/* ── LEFT COLUMN (Helplines & Exports) ── */}
        <div className="w-[20%] flex flex-col gap-4 overflow-y-auto custom-scrollbar pr-1">
          
          {/* DIAL 1930 CTA */}
          <a href="tel:1930" className="block bg-gradient-to-br from-red-600 to-red-500 border-none rounded-xl p-4 text-white shadow-lg shadow-red-500/35 hover:-translate-y-0.5 hover:shadow-red-500/45 transition-all text-decoration-none">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="bg-white/20 p-2 rounded-lg flex items-center justify-center">
                  <Phone className="w-5 h-5 fill-current" />
                </div>
                <div>
                  <div className="text-lg font-black tracking-wide underline">DIAL 1930</div>
                  <div className="text-[10px] text-white/90 leading-tight">
                    Immediate Financial Fraud Reporting (24/7 Helpline)
                  </div>
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-white/70" />
            </div>
          </a>

          {/* Emergency Actions Header */}
          <div className="flex items-center gap-2 mt-1">
            <div className="w-7 h-7 bg-red-50 rounded-lg flex items-center justify-center flex-shrink-0">
              <Bell className="w-4 h-4 text-red-500" />
            </div>
            <span className="text-[11px] font-extrabold text-gray-800 uppercase tracking-widest">Emergency Actions</span>
          </div>

          {/* Action cards */}
          <div className="flex flex-col gap-2">
            {getEmergencyActions().map((action, i) => (
              <div key={i} className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm hover:shadow-md transition-all">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={`text-[9px] font-black text-white px-1.5 py-0.5 rounded uppercase tracking-wider ${action.color}`}>
                    {action.badge}
                  </span>
                  <span className="text-xs font-bold text-gray-900 leading-none">{action.title}</span>
                </div>
                <p className="text-[10px] text-gray-500 leading-relaxed">{action.desc}</p>
              </div>
            ))}
          </div>

          {/* Complaint Package Tracker */}
          <div className="border-t border-gray-200 pt-3 mt-1 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 bg-yellow-50 rounded-lg flex items-center justify-center flex-shrink-0">
                <Folder className="w-4 h-4 text-yellow-600 fill-current" />
              </div>
              <span className="text-[11px] font-extrabold text-gray-800 uppercase tracking-widest">Complaint Package</span>
            </div>

            {/* Status list Box */}
            <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm flex flex-col gap-3">
              
              {/* Classification */}
              <div className="flex items-center gap-2.5">
                {classification ? (
                  <div className="w-4.5 h-4.5 rounded-full bg-green-100 border border-green-500 flex items-center justify-center flex-shrink-0">
                    <Check className="w-2.5 h-2.5 text-green-600 stroke-[3]" />
                  </div>
                ) : (
                  <Clock className="w-4.5 h-4.5 text-gray-400 flex-shrink-0" />
                )}
                <span className={`text-xs ${classification ? 'text-gray-700 font-semibold' : 'text-gray-400 font-normal'}`}>
                  Classification {classification ? '' : '— pending'}
                </span>
              </div>

              {/* Summary Generated */}
              <div className="flex items-center gap-2.5">
                {summaryGenerated ? (
                  <div className="w-4.5 h-4.5 rounded-full bg-green-100 border border-green-500 flex items-center justify-center flex-shrink-0">
                    <Check className="w-2.5 h-2.5 text-green-600 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-4.5 h-4.5 rounded-full border border-blue-500 flex-shrink-0"></div>
                )}
                <span className={`text-xs ${summaryGenerated ? 'text-gray-700 font-semibold' : 'text-gray-400 font-normal'}`}>
                  Summary Generated {summaryGenerated ? '' : '— pending'}
                </span>
              </div>

              {/* Timeline Compiled */}
              <div className="flex items-center gap-2.5">
                {summaryGenerated && timeline.length > 0 ? (
                  <div className="w-4.5 h-4.5 rounded-full bg-green-100 border border-green-500 flex items-center justify-center flex-shrink-0">
                    <Check className="w-2.5 h-2.5 text-green-600 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-4.5 h-4.5 rounded-full border border-blue-500 flex-shrink-0"></div>
                )}
                <span className={`text-xs ${summaryGenerated && timeline.length > 0 ? 'text-gray-700 font-semibold' : 'text-gray-400 font-normal'}`}>
                  Timeline Compiled {summaryGenerated && timeline.length > 0 ? '' : '— pending'}
                </span>
              </div>

              {/* Evidence Logged */}
              <div className="flex items-center gap-2.5">
                {validatedEvidence.length > 0 ? (
                  <div className="w-4.5 h-4.5 rounded-full bg-green-100 border border-green-500 flex items-center justify-center flex-shrink-0">
                    <Check className="w-2.5 h-2.5 text-green-600 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-4.5 h-4.5 rounded-full border border-blue-500 flex-shrink-0"></div>
                )}
                <span className={`text-xs ${validatedEvidence.length > 0 ? 'text-gray-700 font-semibold' : 'text-gray-400 font-normal'}`}>
                  Evidence Logged {validatedEvidence.length > 0 ? '' : '— pending'}
                </span>
              </div>

            </div>

            {/* Export package options */}
            {summaryGenerated && (
              <div className="flex flex-col gap-2 mt-2">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mb-1">Export Report Package</span>
                
                <button onClick={() => handleExport('pdf')} className="flex items-center gap-2 w-full text-left px-3 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 text-xs font-semibold rounded-lg shadow-sm">
                  <FileText className="w-4 h-4 text-red-500" />
                  Download PDF Report
                </button>
                
                <button onClick={() => handleExport('txt')} className="flex items-center gap-2 w-full text-left px-3 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 text-xs font-semibold rounded-lg shadow-sm">
                  <FileText className="w-4 h-4 text-blue-500" />
                  Download TXT File
                </button>

                <button onClick={() => handleExport('md')} className="flex items-center gap-2 w-full text-left px-3 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 text-xs font-semibold rounded-lg shadow-sm">
                  <FileText className="w-4 h-4 text-gray-600" />
                  Download Markdown
                </button>

                <button onClick={() => handleExport('html')} className="flex items-center gap-2 w-full text-left px-3 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 text-xs font-semibold rounded-lg shadow-sm">
                  <Printer className="w-4 h-4 text-green-500" />
                  Print Layout View
                </button>
              </div>
            )}
          </div>

        </div>

        {/* ── CENTER COLUMN (AI Chat & Case File) ── */}
        <div className="w-[55%] flex flex-col gap-4 overflow-hidden px-1 h-full min-h-0">
          
          {/* Chat Feed Box */}
          <div className="bg-white border border-gray-200 rounded-2xl flex flex-col flex-1 min-h-0 shadow-sm relative overflow-hidden">
            
            {/* Messages Feed */}
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 custom-scrollbar">
              
              {messages.length <= 1 ? (
                /* Empty state / features guide */
                <div className="flex flex-col items-center justify-center py-6 text-center my-auto">
                  <div className="relative w-24 h-24 mb-4 flex items-center justify-center">
                    <div className="absolute inset-0 bg-[#0B3C5D]/5 rounded-full scale-125 animate-pulse"></div>
                    <div className="w-16 h-16 bg-[#0B3C5D] rounded-full flex items-center justify-center text-white shadow-lg shadow-[#0B3C5D]/20 z-10">
                      <Cpu className="w-8 h-8" />
                    </div>
                  </div>
                  <h3 className="text-base font-bold text-gray-900">Describe the incident</h3>
                  <p className="text-xs text-gray-500 max-w-sm mt-1 px-4">
                    Share as many details as you can. The more information you provide, the better I can classify and assist you.
                  </p>

                  <div className="grid grid-cols-3 gap-3 w-full max-w-lg mt-8 px-4">
                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 flex flex-col items-center">
                      <div className="p-1.5 bg-green-50 text-green-600 rounded-lg mb-2">
                        <Shield className="w-4 h-4" />
                      </div>
                      <span className="text-[10px] font-bold text-gray-900 text-center">Secure &amp; Private</span>
                      <p className="text-[9px] text-gray-500 text-center mt-0.5">Your inputs remain fully confidential.</p>
                    </div>

                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 flex flex-col items-center">
                      <div className="p-1.5 bg-indigo-50 text-indigo-600 rounded-lg mb-2">
                        <Cpu className="w-4 h-4" />
                      </div>
                      <span className="text-[10px] font-bold text-gray-900 text-center">AI Diagnostics</span>
                      <p className="text-[9px] text-gray-500 text-center mt-0.5">Automated playbook recommendations.</p>
                    </div>

                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 flex flex-col items-center">
                      <div className="p-1.5 bg-blue-50 text-blue-600 rounded-lg mb-2">
                        <Building className="w-4 h-4" />
                      </div>
                      <span className="text-[10px] font-bold text-gray-900 text-center">Govt Aligned</span>
                      <p className="text-[9px] text-gray-500 text-center mt-0.5">Complies with cybercrime.gov.in.</p>
                    </div>
                  </div>
                </div>
              ) : (
                /* Dialogue lists */
                messages.map((msg, i) => {
                  const isAssistant = msg.role === 'assistant';
                  return (
                    <div key={i} className={`flex gap-3 max-w-[85%] ${isAssistant ? 'self-start' : 'self-end flex-row-reverse'}`}>
                      
                      {/* Avatar */}
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm ${
                        isAssistant ? 'bg-[#0B3C5D] text-white' : 'bg-gray-200 text-gray-700'
                      }`}>
                        {isAssistant ? '🤖' : '👤'}
                      </div>

                      {/* Content box */}
                      <div className="flex flex-col gap-1.5 w-full">
                        <div className={`p-3 rounded-2xl text-xs leading-relaxed shadow-sm ${
                          isAssistant ? 'bg-gray-100 text-gray-800 rounded-tl-none' : 'bg-[#0B3C5D] text-white rounded-tr-none'
                        }`}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]} className="chat-markdown">
                            {msg.content}
                          </ReactMarkdown>
                        </div>

                        {/* Render Inline Checkbox checklist under the text bubble if msg.type is evidence_checklist */}
                        {isAssistant && msg.type === 'evidence_checklist' && (
                          <div className="w-full bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm flex flex-col divide-y divide-gray-150 mt-1">
                            {evidenceItemsList.length > 0 ? (
                              evidenceItemsList.map(it => (
                                <label key={it.id} className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-2.5 transition-all select-none">
                                  <input 
                                    type="checkbox"
                                    checked={!!evidence[it.id]}
                                    onChange={() => handleToggleEvidence(it.id)}
                                    className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary accent-primary"
                                  />
                                  <span className="text-gray-700 text-xs">{it.label}</span>
                                </label>
                              ))
                            ) : (
                              <div className="p-3 text-xs text-gray-400 italic text-center">No checklist items available.</div>
                            )}
                          </div>
                        )}

                        {/* Quick Reply Chip Selection */}
                        {isAssistant && msg.type === 'quick_reply' && i === messages.length - 1 && (
                          <div className="flex flex-wrap gap-2 mt-1.5">
                            {msg.options?.map((opt, oIdx) => (
                              <button
                                key={oIdx}
                                onClick={() => handleSendMessage(opt)}
                                className="px-3.5 py-1.5 bg-white border border-[#328CC1] text-[#328CC1] hover:bg-[#328CC1]/10 text-xs font-semibold rounded-full transition-all shadow-sm"
                              >
                                {opt}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                    </div>
                  );
                })
              )}
              {isChatLoading && (
                <div className="self-start flex gap-3 max-w-[80%] items-center">
                  <div className="w-8 h-8 rounded-full bg-[#0B3C5D] text-white flex items-center justify-center">🤖</div>
                  <div className="p-3 bg-gray-100 rounded-2xl rounded-tl-none text-xs text-gray-500 italic flex items-center gap-1.5 shadow-sm">
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></span>
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce delay-75"></span>
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce delay-150"></span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Chat Input Pinned Footer */}
            <div className="p-4 border-t border-gray-150 bg-white">
              <div className="flex items-center border border-gray-250 rounded-xl bg-white px-3 py-1.5 focus-within:ring-1 focus-within:ring-primary focus-within:border-primary">
                <input
                  type="text"
                  value={userInput}
                  onChange={e => setUserInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendMessage(userInput)}
                  disabled={isChatLoading || isRecording || isTranscribing}
                  placeholder={
                    isRecording 
                      ? "Recording audio... speak clearly." 
                      : isTranscribing 
                        ? "Transcribing voice via Groq Whisper..." 
                        : stage === 'stage_4_evidence' 
                          ? "Evidence checklist open below. You can still message..." 
                          : "Tell me what happened — I'm here to help..."
                  }
                  className="flex-1 bg-transparent border-none outline-none text-xs text-gray-700 placeholder-gray-400 py-1"
                />

                {/* Voice Input Button */}
                <button
                  type="button"
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isChatLoading || isTranscribing}
                  className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all shadow-sm mr-2 ${
                    isRecording 
                      ? 'bg-red-500 hover:bg-red-600 text-white animate-pulse' 
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
                  }`}
                  title={isRecording ? "Stop recording" : "Record voice input"}
                >
                  {isTranscribing ? (
                    <div className="w-3.5 h-3.5 border-2 border-gray-600 border-t-transparent rounded-full animate-spin"></div>
                  ) : isRecording ? (
                    <Square className="w-3.5 h-3.5 fill-current" />
                  ) : (
                    <Mic className="w-3.5 h-3.5" />
                  )}
                </button>

                <button 
                  onClick={() => handleSendMessage(userInput)}
                  disabled={isChatLoading || isRecording || isTranscribing || !userInput.trim()}
                  className="w-8 h-8 rounded-full bg-[#328CC1] hover:bg-[#0B3C5D] text-white flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-40 shadow-sm"
                >
                  <Send className="w-3.5 h-3.5 fill-current translate-x-[0.5px]" />
                </button>
              </div>
            </div>


          </div>

          {/* Active Case File Box */}
          <div className="bg-white border border-gray-200 rounded-2xl p-5 shadow-sm flex flex-col gap-3 flex-1 min-h-0 overflow-hidden">
            
            {/* Header / Classification dropdown */}
            <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 flex-shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-800 uppercase tracking-widest">Active Case File</span>
              </div>
              {classification && (
                <div className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-blue-50 border border-blue-200 rounded text-[10px] font-bold text-blue-700">
                  CONFIDENCE: {Math.round(confidenceScore * 100)}%
                </div>
              )}
            </div>

            {/* Scrollable contents container */}
            <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col gap-4 pr-1">
              
              {/* Classification selectors */}
              <div className="grid grid-cols-1 gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Classification Override</label>
                  <span className="text-[9.5px] text-gray-400 font-semibold italic">Based on National Cyber Crime Reporting Portal</span>
                </div>
                <select
                  value={classification?.subcategory_id || ''}
                  onChange={e => handleClassificationOverride(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 bg-gray-50 focus:outline-none focus:ring-1 focus:ring-[#0B3C5D]"
                >
                  <option value="" disabled>-- Select manual category override --</option>
                  {config.subcategories.map(sub => {
                    const cat = config.categories.find(c => c.id === sub.category_id);
                    const catPrefix = cat ? `${cat.name} — ` : '';
                    return (
                      <option key={sub.id} value={sub.id}>
                        {catPrefix}{sub.name}
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* AI Summary textarea */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Incident Summary</label>
                  {summaryGenerated && (
                    <button 
                      onClick={() => setEditingSummary(!editingSummary)}
                      className="text-xs text-[#328CC1] hover:underline flex items-center gap-1 font-semibold"
                    >
                      <Edit2 className="w-3 h-3" />
                      {editingSummary ? 'Done' : 'Edit'}
                    </button>
                  )}
                </div>
                {editingSummary ? (
                  <textarea
                    value={editedSummaryText}
                    onChange={e => {
                      setEditedSummaryText(e.target.value);
                      setSummary(e.target.value);
                    }}
                    rows={4}
                    className="w-full p-3 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-[#0B3C5D]"
                  />
                ) : (
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-600 leading-relaxed min-h-[70px]">
                    {summary || (
                      <span className="text-gray-400 italic">No summary generated. Fill in the chat inputs to compile your incident.</span>
                    )}
                  </div>
                )}
              </div>

              {/* Timeline Editor */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Timeline Entries</label>
                  {summaryGenerated && (
                    <button 
                      onClick={handleAddTimelineRow}
                      className="text-xs text-[#328CC1] hover:underline flex items-center gap-1 font-semibold"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Entry
                    </button>
                  )}
                </div>
                
                <div className="border border-gray-200 rounded-lg overflow-hidden">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200 text-gray-500 font-bold">
                        <th className="p-2.5 w-[30%]">Date/Time</th>
                        <th className="p-2.5 w-[60%]">Event Details</th>
                        <th className="p-2.5 w-[10%] text-center">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timeline.length > 0 ? (
                        timeline.map((item, idx) => (
                          <tr key={idx} className="border-b border-gray-150 hover:bg-gray-50/50">
                            <td className="p-1">
                              <input 
                                type="text" 
                                value={item.time} 
                                onChange={e => handleTimelineChange(idx, 'time', e.target.value)}
                                className="w-full px-2 py-1 bg-transparent hover:bg-gray-100 focus:bg-white focus:outline-none rounded text-xs font-semibold text-gray-700"
                              />
                            </td>
                            <td className="p-1">
                              <input 
                                type="text" 
                                value={item.event} 
                                onChange={e => handleTimelineChange(idx, 'event', e.target.value)}
                                className="w-full px-2 py-1 bg-transparent hover:bg-gray-100 focus:bg-white focus:outline-none rounded text-xs text-gray-600"
                              />
                            </td>
                            <td className="p-1 text-center">
                              <button 
                                onClick={() => handleRemoveTimelineRow(idx)}
                                className="p-1 text-red-500 hover:bg-red-50 rounded"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="3" className="p-4 text-center text-gray-400 italic">No timeline entries generated yet.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

            </div>



          </div>

        </div>

        {/* ── RIGHT COLUMN (Playbook & Scam Carousel) ── */}
        <div className="w-[25%] flex flex-col gap-4 overflow-y-auto custom-scrollbar pl-1">
          
          {/* Incident Playbook Card */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm flex flex-col gap-3">
            
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center">
                  <BookOpen className="w-4 h-4" />
                </div>
                <h2 className="text-xs font-bold text-gray-800 uppercase tracking-widest">Incident Playbook</h2>
              </div>
            </div>

            {/* Playbook contents (Accordions) */}
            {!playbook ? (
              /* Locked Placeholder */
              <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 flex gap-3 items-center">
                <div className="w-12 h-14 bg-gray-100 border border-gray-200 rounded-lg flex flex-col items-center justify-center flex-shrink-0 relative">
                  <Lock className="w-4 h-4 text-gray-400" />
                </div>
                <div>
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-0.5">LOCKED</span>
                  <p className="text-[11px] text-gray-500 leading-normal">
                    Describe your case in chat. The AI will classify and unlock response steps automatically.
                  </p>
                </div>
              </div>
            ) : !playbook.available ? (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-amber-800 text-xs leading-normal">
                {playbook.message}
              </div>
            ) : (
              /* Accordions */
              <div className="flex flex-col gap-2">
                {Object.entries(playbook.sections).map(([title, content]) => {
                  const isExpanded = !!expandedPlaybookSections[title];
                  return (
                    <div key={title} className="border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                      <button 
                        onClick={() => setExpandedPlaybookSections({
                          ...expandedPlaybookSections,
                          [title]: !isExpanded
                        })}
                        className="w-full flex items-center justify-between px-3 py-2.5 bg-gray-55 hover:bg-gray-100 text-xs font-bold text-gray-800 text-left transition-all"
                      >
                        <span>{title}</span>
                        <ChevronRight className={`w-3.5 h-3.5 text-gray-500 transition-all ${isExpanded ? 'rotate-90' : ''}`} />
                      </button>
                      
                      {isExpanded && (
                        <div className="p-3 bg-white text-[11px] text-gray-600 leading-relaxed border-t border-gray-150 playbook-markdown">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

          </div>

          {/* Trending Scam Alerts Carousel */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm flex flex-col gap-3">
            
            {/* Header */}
            <div className="flex items-center gap-2 border-b border-gray-100 pb-3">
              <div className="p-1.5 bg-red-50 text-red-500 rounded-lg flex items-center justify-center">
                <Bell className="w-4 h-4" />
              </div>
              <h2 className="text-xs font-bold text-gray-800 uppercase tracking-widest">Trending Scam Alerts</h2>
            </div>

            {/* Slider cards container */}
            {config.threat_intelligence.length > 0 ? (
              (() => {
                const scam = config.threat_intelligence[scamIndex];
                if (!scam) return null;
                const isCritical = scam.severity?.toUpperCase() === 'CRITICAL';
                
                return (
                  <div className="flex flex-col gap-3">
                    
                    {/* Active Scam Slide */}
                    <div className="bg-[#FAFAFA] border border-gray-200 rounded-xl p-3.5 shadow-sm min-h-[260px] flex flex-col justify-between">
                      <div>
                        {/* Title & badge */}
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <h3 className="text-[12px] font-bold text-gray-950 leading-tight">{scam.scam_name}</h3>
                          <span className={`text-[8px] font-black text-white px-1.5 py-0.5 rounded uppercase tracking-wider ${
                            isCritical ? 'bg-red-500' : 'bg-amber-500'
                          }`}>
                            {scam.severity}
                          </span>
                        </div>

                        {/* Description */}
                        <p className="text-[10px] text-gray-600 leading-relaxed mb-3">{scam.description}</p>

                        {/* Phishing script box */}
                        <div className="bg-[#F8FAFC] border-l-3 border-blue-500 rounded p-2 text-[9px] font-mono text-gray-700 leading-normal mb-2 max-h-[80px] overflow-y-auto custom-scrollbar">
                          <strong>Example Phishing Script:</strong><br />
                          {scam.example_script}
                        </div>

                        {/* Defense step box */}
                        <div className="bg-[#F0FDF4] border-l-3 border-green-600 rounded p-2 text-[9px] font-medium text-green-950 leading-normal">
                          <strong>Victim Defense Step:</strong><br />
                          {scam.defense_step}
                        </div>
                      </div>
                    </div>

                    {/* Slider Navigation Bar */}
                    <div className="flex items-center justify-between px-1 mt-1">
                      
                      <button 
                        onClick={() => setScamIndex(prev => (prev === 0 ? config.threat_intelligence.length - 1 : prev - 1))}
                        className="p-1.5 border border-gray-200 bg-white hover:bg-gray-50 rounded-lg shadow-sm text-gray-700"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>

                      {/* Paginate dots */}
                      <div className="flex items-center gap-1.5">
                        {config.threat_intelligence.map((_, dotIdx) => (
                          <div 
                            key={dotIdx}
                            onClick={() => setScamIndex(dotIdx)}
                            className={`w-2 h-2 rounded-full cursor-pointer transition-all ${
                              scamIndex === dotIdx ? 'bg-red-500 scale-110' : 'bg-gray-300'
                            }`}
                          />
                        ))}
                      </div>

                      <button 
                        onClick={() => setScamIndex(prev => (prev === config.threat_intelligence.length - 1 ? 0 : prev + 1))}
                        className="p-1.5 border border-gray-200 bg-white hover:bg-gray-50 rounded-lg shadow-sm text-gray-700"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>

                    </div>

                  </div>
                );
              })()
            ) : (
              <div className="p-4 text-center text-gray-400 italic text-xs">Loading scam updates...</div>
            )}

          </div>

        </div>

      </div>

    </div>
  );
}
