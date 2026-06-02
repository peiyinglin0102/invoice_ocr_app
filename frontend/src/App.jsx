import React, { useState, useRef, useCallback, useMemo } from 'react';
import {
  UploadCloud, Loader2, FileText, CheckCircle,
  AlertCircle, RefreshCw, Download, Copy, ChevronUp, ChevronDown,
  Receipt, Settings, ClipboardList, ShoppingCart, PieChart, DownloadCloud
} from 'lucide-react';
import Plot from 'react-plotly.js';

// ─────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────
const BACKEND_URL = 'http://localhost:8000';

const CATEGORY_COLORS = {
    '餐飲': '#FC8181',
    '超商/超市': '#F6AD55',
    '伴手禮/土特產': '#ED8936',
    '零食/飲料': '#ED64A6',
    '藥妝/美妝': '#63B3ED',
    '醫療保健': '#68D391',
    '服飾/鞋包': '#B794F4',
    '精品/奢侈品': '#9F7AEA',
    '動漫/玩具/周邊': '#4FD1C5',
    '居家/生活用品': '#319795',
    '電子產品/3C': '#4299E1',
    '交通': '#ECC94B',
    '住宿': '#5A67D8',
    '門票/娛樂': '#667EEA',
    '稅金/服務費': '#A0AEC0',
    '免稅/折扣': '#F56565',
    '文具/書籍': '#ED8936',
    '其他': '#CBD5E0',
}

const STAGES = [
  { id: 1, label: '正在辨識發票文字...', from: 0,  to: 33  },
  { id: 2, label: '正在分析品項並整理資料...', from: 33, to: 66  },
  { id: 3, label: '正在查詢歷史匯率並換算...', from: 66, to: 100 },
];

const OCR_LANGS = [
  { value: 'japan',  label: '日文 (Japanese)' },
  { value: 'korean', label: '韓文 (Korean)' },
  { value: 'en',     label: '英文 (English)' },
  { value: 'ch',     label: '中文 (Chinese)' },
];

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────
function catBadgeStyle(category) {
  const bg = CATEGORY_COLORS[category] || '#CBD5E0';
  return {
    backgroundColor: bg + '28',
    color: bg,
    border: `1px solid ${bg}66`,
  };
}

function fmtNumber(n) {
  return Number(n).toLocaleString('zh-TW');
}

// Build UTF-8 BOM CSV for Excel compatibility
function buildCsv(items, currency) {
  const BOM = '﻿';
  const headers = ['原始文字', '品項翻譯', `單價(${currency})`, '數量', '稅務標記', '分類', '台幣小計(NT$)'];
  const rows = items.map(it => [
    `"${(it.original_name  || '').replace(/"/g, '""')}"`,
    `"${(it.translated_name|| '').replace(/"/g, '""')}"`,
    it.unit_price,
    it.quantity,
    `"${it.tax_flag || '—'}"`,
    `"${it.category || ''}"`,
    it.twd_subtotal,
  ].join(','));
  return BOM + [headers.join(','), ...rows].join('
');
}

function downloadBlob(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

/** Three-stage progress indicator */
function ProgressPanel({ stage }) {
  const pct = stage >= 3 ? 100 : stage === 2 ? 66 : stage === 1 ? 33 : 5;
  return (
    <div className="progress-container" role="status" aria-live="polite">
      <div className="progress-label">{STAGES[Math.min(stage, 2)].label}</div>
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="stage-steps">
        {STAGES.map((s, i) => {
          const isDone   = stage > i;
          const isActive = stage === i;
          return (
            <div key={s.id} className={`stage-step ${isDone ? 'done' : isActive ? 'active' : ''}`}>
              <span className="stage-dot" />
              {isDone ? '✓ ' : ''}{s.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Metric card */
function MetricCard({ label, value, highlight }) {
  return (
    <div className={`metric-card${highlight ? ' twd-card' : ''}`}>
      <div className="metric-label">{label}</div>
      <div className={`metric-value${highlight ? ' twd-highlight' : ''}`}>{value}</div>
    </div>
  );
}

/** Sortable data table */
function ItemsTable({ items, currency }) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sorted = useMemo(() => {
    if (!sortKey) return items;
    return [...items].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv), 'zh-TW')
        : String(bv).localeCompare(String(av), 'zh-TW');
    });
  }, [items, sortKey, sortDir]);

  const SortIcon = ({ col }) => {
    if (sortKey !== col) return <ChevronUp size={12} style={{ opacity: 0.3 }} />;
    return sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  const cols = [
    { key: 'translated_name', label: '品項翻譯' },
    { key: 'unit_price',      label: `單價(${currency})` },
    { key: 'quantity',        label: '數量' },
    { key: 'tax_flag',        label: '稅務標記' },
    { key: 'category',        label: '分類' },
    { key: 'twd_subtotal',    label: '台幣小計' },
  ];

  return (
    <div className="table-wrapper" tabIndex={0} aria-label="購買明細表格">
      <table className="data-table">
        <thead>
          <tr>
            {cols.map(c => (
              <th
                key={c.key}
                onClick={() => toggleSort(c.key)}
                aria-sort={sortKey === c.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                tabIndex={0}
                onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && toggleSort(c.key)}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  {c.label} <SortIcon col={c.key} />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, idx) => (
            <tr key={idx}>
              <td>
                <span style={{ fontWeight: 600 }}>{item.translated_name}</span>
                {item.original_name && (
                  <div className="original-name-sub">{item.original_name}</div>
                )}
              </td>
              <td>{fmtNumber(item.unit_price)}</td>
              <td>{item.quantity}</td>
              <td>
                {item.tax_flag
                  ? <span className="tax-badge">{item.tax_flag}</span>
                  : <span className="tax-none">—</span>
                }
              </td>
              <td>
                <span className="cat-badge" style={catBadgeStyle(item.category)}>
                  {item.category}
                </span>
              </td>
              <td className="twd-subtotal">NT$ {fmtNumber(item.twd_subtotal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Plotly pie chart */
function CategoryPie({ items }) {
  const agg = useMemo(() => {
    const totals = {};
    items.forEach(it => {
      const cat = it.category || '其他';
      totals[cat] = (totals[cat] || 0) + it.twd_subtotal;
    });
    return totals;
  }, [items]);

  const labels  = Object.keys(agg);
  const values  = Object.values(agg);
  const colors  = labels.map(l => CATEGORY_COLORS[l] || '#CBD5E0');

  return (
    <div className="chart-container" aria-label="本次消費分類比例圓餅圖">
      <Plot
        data={[{
          type: 'pie',
          labels,
          values,
          marker: { colors },
          textinfo: 'percent+label',
          textposition: 'inside',
          hovertemplate: '<b>%{label}</b><br>金額：NT$ %{value:,}<br>佔比：%{percent}<extra></extra>',
          sort: false,
        }]}
        layout={{
          title: { text: '本次消費分類比例', font: { color: '#E2E8F0', family: 'Outfit', size: 16 } },
          paper_bgcolor: 'transparent',
          plot_bgcolor:  'transparent',
          font: { color: '#A0AEC0', family: 'Inter' },
          legend: {
            orientation: 'v',
            yanchor: 'top',
            y: 1,
            xanchor: 'left',
            x: 1.02,
            font: { color: '#CBD5E0' },
          },
          margin: { l: 10, r: 160, t: 50, b: 10 },
          showlegend: true,
        }}
        config={{ scrollZoom: false, displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Main App
// ─────────────────────────────────────────────
export default function App() {
  const [apiKey,       setApiKey]       = useState('');
  const [ocrLang,      setOcrLang]      = useState('japan');
  const [file,         setFile]         = useState(null);
  const [previewUrl,   setPreviewUrl]   = useState(null);
  const [dragActive,   setDragActive]   = useState(false);
  const [stage,        setStage]        = useState(-1);   // -1=idle, 0/1/2=processing stages
  const [result,       setResult]       = useState(null);
  const [error,        setError]        = useState(null);
  const [warning,      setWarning]      = useState(null);
  const fileInputRef = useRef(null);

  const isProcessing = stage >= 0;
  const canStart     = apiKey.trim() && file && !isProcessing;

  // ── File Handling ──
  const applyFile = useCallback((f) => {
    if (!f) return;
    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowed.includes(f.type)) {
      setError('不支援的檔案格式，請上傳 JPG、PNG 或 WebP。');
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setError('檔案大小超過 10MB 上限，請壓縮後重新上傳。');
      return;
    }
    setError(null);
    setResult(null);
    setWarning(null);
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
  }, []);

  const handleDragOver  = (e) => { e.preventDefault(); setDragActive(true); };
  const handleDragLeave = ()  => setDragActive(false);
  const handleDrop      = (e) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) applyFile(e.dataTransfer.files[0]);
  };
  const handleFileChange = (e) => {
    if (e.target.files?.[0]) applyFile(e.target.files[0]);
  };

  const handleContextMenu = (e) => e.preventDefault();

  // ── Process Invoice ──
  const processInvoice = async () => {
    if (!canStart) return;
    setError(null);
    setWarning(null);
    setResult(null);
    setStage(0);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('api_key', apiKey.trim());
    formData.append('ocr_lang', ocrLang);

    try {
      await delay(300);
      setStage(1);

      const res = await fetch(`${BACKEND_URL}/api/process_invoice`, {
        method: 'POST',
        body: formData,
      });

      setStage(2);
      await delay(200);

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        const detail  = errJson.detail || `HTTP ${res.status}`;
        throw new Error(detail);
      }

      const json = await res.json();
      if (!json.success) throw new Error(json.error_message || '處理失敗');

      if (json.data.is_fallback_rate) {
        setWarning(
          `即時匯率查詢失敗，目前使用估算匯率（1 ${json.data.currency} ≈ ${json.data.exchange_rate.toFixed(4)} TWD），數據僅供參考。`
        );
      }

      setResult(json.data);
      setStage(-1);
    } catch (err) {
      setStage(-1);
      const msg = err.message || '未知錯誤';
      if (msg.includes('ERR-004') || msg.includes('API') || msg.includes('401')) {
        setError(`系統授權失敗，請確認 API Key 是否正確。`);
      } else if (msg.includes('ERR-003')) {
        setError(`系統處理資料時發生異常，已重試仍失敗，請稍後再試。`);
      } else if (msg.includes('ERR-002')) {
        setError(`無法提取圖片中的文字。圖片可能過於模糊或角度不佳，請重新拍攝。`);
      } else if (msg.includes('ERR-001')) {
        setError(`${msg.replace('ERR-001：', '')}`);
      } else if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
        setError(`無法連線至後端伺服器，請確認 FastAPI 服務已啟動。`);
      } else {
        setError(`系統錯誤：${msg}`);
      }
    }
  };

  const delay = (ms) => new Promise(r => setTimeout(r, ms));

  // ── Export ──
  const exportCsv = () => {
    if (!result) return;
    const csv = buildCsv(result.items, result.currency);
    downloadBlob(csv, `invoice_${result.invoice_date}.csv`, 'text/csv;charset=utf-8');
  };

  const exportJson = () => {
    if (!result) return;
    const payload = JSON.stringify(result, null, 2);
    downloadBlob(payload, `invoice_${result.invoice_date}.json`, 'application/json');
  };

  const copyJson = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    } catch {/* ignore */}
  };

  // ─────────────────────────────────────────
  return (
    <div className="app-container">
      {/* ── Header ── */}
      <header className="app-header">
        <h1 style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
          <Receipt size={28} /> 智能外幣發票理財系統
        </h1>
        <p>拍照上傳發票，系統自動辨識、翻譯、分類，即時換算台幣消費金額。</p>
      </header>

      <div className="layout-grid">
        {/* ══ SIDEBAR ══ */}
        <aside className="sidebar">
          <div className="glass-card">
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Settings size={20} /> 系統設定
            </h2>

            {/* API Key */}
            <div className="form-group">
              <label className="form-label" htmlFor="api-key-input">Gemini API Key</label>
              <input
                id="api-key-input"
                type="password"
                className="form-input"
                placeholder="輸入您的 Gemini API 金鑰"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                aria-describedby="api-key-status"
                autoComplete="off"
              />
              <div id="api-key-status" className={`api-key-status ${apiKey.trim() ? 'set' : 'unset'}`}>
                {apiKey.trim()
                  ? <><CheckCircle size={14} /> API Key 已設定（遮罩顯示）</>
                  : <><AlertCircle size={14} /> 尚未設定 API Key</>
                }
              </div>
            </div>

            {/* OCR Language */}
            <div className="form-group">
              <label className="form-label" htmlFor="ocr-lang-select">發票主要語系</label>
              <select
                id="ocr-lang-select"
                className="form-select"
                value={ocrLang}
                onChange={e => setOcrLang(e.target.value)}
              >
                {OCR_LANGS.map(l => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
            </div>

            {/* Usage guide */}
            <div style={{ marginTop: '0.5rem' }}>
              <p className="form-label" style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ClipboardList size={16} /> 使用說明
              </p>
              <ol className="usage-guide">
                {['輸入 Gemini API Key', '選擇發票語系', '上傳發票圖片', '點擊「開始辨識」', '查看分析報告並匯出'].map((txt, i) => (
                  <li key={i}>
                    <span className="step-num">{i + 1}</span>
                    <span>{txt}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </aside>

        {/* ══ MAIN PANEL ══ */}
        <main>
          <div className="glass-card">
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <UploadCloud size={20} /> 上傳發票圖片
            </h2>

            {/* Upload Zone */}
            <div
              id="upload-zone"
              className={`upload-zone${dragActive ? ' drag-active' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onContextMenu={handleContextMenu}
              role="button"
              tabIndex={0}
              aria-label="上傳發票圖片，點擊或拖曳圖片至此"
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click();
              }}
            >
              <UploadCloud className="upload-zone-icon" aria-hidden="true" />
              <p className="main-text">點擊選擇或拖曳圖片至此</p>
              <p className="sub-text">支援 JPG / PNG / WebP｜最大 10 MB｜行動裝置可直接拍照</p>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                onChange={handleFileChange}
                aria-label="選擇發票圖片"
                tabIndex={-1}
              />
            </div>

            {/* Preview */}
            {previewUrl && file && (
              <div className="preview-box">
                <img src={previewUrl} alt="已上傳發票預覽" />
                <div className="preview-info">
                  <CheckCircle size={14} color="#68D391" />
                  <span>{file.name}（{(file.size / 1024).toFixed(1)} KB）</span>
                </div>
              </div>
            )}

            {/* Alerts */}
            {error && (
              <div className="alert alert-error" role="alert" style={{ marginTop: '1rem', fontSize: 14 }}>
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}
            {warning && (
              <div className="alert alert-warning" role="status" style={{ marginTop: '1rem' }}>
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>{warning}</span>
              </div>
            )}

            {/* Action Button */}
            <button
              className="btn-primary"
              id="start-btn"
              onClick={processInvoice}
              disabled={!canStart}
              aria-busy={isProcessing}
              aria-label={isProcessing ? '辨識處理中，請稍候' : '開始辨識發票'}
            >
              {isProcessing
                ? <><Loader2 size={18} className="spinner" /> 處理中，請稍候...</>
                : <><RefreshCw size={18} /> 開始辨識</>
              }
            </button>

            {/* Progress */}
            {isProcessing && <ProgressPanel stage={stage} />}

            {/* Success flash */}
            {result && !isProcessing && (
              <div className="alert alert-success" role="status" style={{ marginTop: '1rem' }}>
                <CheckCircle size={16} style={{ flexShrink: 0 }} />
                <span>發票辨識與分析已完成！請查看下方財務報告。</span>
              </div>
            )}
          </div>

          {/* ══ RESULTS SECTION ══ */}
          {result && (
            <div className="results-section" style={{ marginTop: '1.75rem' }}>

              {/* Financial Report Card */}
              <div className="glass-card">
                <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileText size={20} /> 財務分析報告
                </h2>

                {/* Metrics — 4 columns */}
                <div className="metrics-grid">
                  <MetricCard
                    label="消費日期"
                    value={result.invoice_date || '—'}
                  />
                  <MetricCard
                    label="外幣總額"
                    value={`${fmtNumber(result.total_foreign_amount)} ${result.currency}`}
                  />
                  <MetricCard
                    label="適用匯率"
                    value={result.exchange_rate.toFixed(4)}
                  />
                  <MetricCard
                    label="台幣總花費"
                    value={`NT$ ${fmtNumber(result.total_twd)}`}
                    highlight
                  />
                </div>
              </div>

              {/* Items Table */}
              <div className="glass-card">
                <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShoppingCart size={20} /> 購買明細表格
                </h2>
                <ItemsTable items={result.items} currency={result.currency} />
              </div>

              {/* Pie Chart */}
              <div className="glass-card">
                <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <PieChart size={20} /> 本次消費分類比例
                </h2>
                <CategoryPie items={result.items} />
              </div>

              {/* Export */}
              <div className="glass-card">
                <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <DownloadCloud size={20} /> 匯出報告
                </h2>
                <div className="export-grid">
                  <button className="btn-export" onClick={exportCsv} aria-label="下載 CSV 報告">
                    <Download size={16} /> 下載 CSV（Excel 相容）
                  </button>
                  <button className="btn-export" onClick={exportJson} aria-label="下載 JSON 報告">
                    <Download size={16} /> 下載 JSON
                  </button>
                  <button className="btn-export" onClick={copyJson} aria-label="複製 JSON 至剪貼簿"
                    style={{ gridColumn: '1 / -1' }}>
                    <Copy size={16} /> 複製 JSON
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
