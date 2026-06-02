import React, { useState, useRef } from 'react';
import { UploadCloud, Loader2, FileText, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

function App() {
  const [file, setFile] = useState(null);
  const [provider, setProvider] = useState('Gemini');
  const [apiKey, setApiKey] = useState('');
  const [ocrLang, setOcrLang] = useState('japan');
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const processInvoice = async () => {
    if (!file || !apiKey) {
      setError("請確認已上傳圖片並輸入 API Key");
      return;
    }
    
    setIsProcessing(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('llm_provider', provider.toLowerCase());
    formData.append('api_key', apiKey);
    formData.append('ocr_lang', ocrLang);

    try {
      // Assuming backend runs on localhost:8000
      const response = await fetch('http://localhost:8000/api/process_invoice', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "伺服器處理失敗");
      }

      const data = await response.json();
      setResult(data.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  const renderDashboard = () => {
    if (!result) return null;
    const { receipt_info, items } = result;
    
    // Process Data for Pie Chart
    const categoryTotals = {};
    items.forEach(item => {
      const cat = item.category || '其他';
      const twd = item.quantity * item.unit_price * receipt_info.exchange_rate;
      if (!categoryTotals[cat]) categoryTotals[cat] = 0;
      categoryTotals[cat] += twd;
    });
    
    const chartData = Object.keys(categoryTotals).map(key => ({
      name: key,
      value: Math.round(categoryTotals[key])
    }));
    
    const COLORS = ['#4F46E5', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

    return (
      <div className="glass-card" style={{ gridColumn: '1 / -1' }}>
        <h2 className="card-title">
          <FileText className="text-primary" /> 財務分析報告
        </h2>
        
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-title">消費日期</div>
            <div className="metric-value">{receipt_info.date}</div>
          </div>
          <div className="metric-card">
            <div className="metric-title">外幣總額</div>
            <div className="metric-value">{receipt_info.total_amount_foreign} {receipt_info.currency}</div>
          </div>
          <div className="metric-card">
            <div className="metric-title">所用匯率</div>
            <div className="metric-value">{receipt_info.exchange_rate.toFixed(4)}</div>
          </div>
          <div className="metric-card">
            <div className="metric-title">總稅額 ({receipt_info.currency})</div>
            <div className="metric-value" style={{ color: '#059669' }}>{receipt_info.tax_amount || 0}</div>
          </div>
          <div className="metric-card" style={{ borderColor: '#4F46E5', borderWidth: '2px' }}>
            <div className="metric-title">台幣總花費</div>
            <div className="metric-value metric-highlight">NT$ {Math.round(receipt_info.twd_total)}</div>
          </div>
        </div>

        <div className="main-grid" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <div>
            <h3 className="card-title" style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>🛒 購買明細清單</h3>
            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>品項翻譯</th>
                    <th>單價 ({receipt_info.currency})</th>
                    <th>數量</th>
                    <th>稅務</th>
                    <th>分類</th>
                    <th>台幣小計</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 500 }}>{item.translated_name}
                        <div style={{ fontSize: '0.8rem', color: '#6B7280' }}>{item.original_name}</div>
                      </td>
                      <td>{item.unit_price}</td>
                      <td>{item.quantity}</td>
                      <td>
                        <span className={item.tax_free ? "tax-free-badge" : "tax-inc-badge"}>
                          {item.tax_free ? "免稅" : "含稅"}
                        </span>
                      </td>
                      <td><span className="category-badge">{item.category}</span></td>
                      <td style={{ fontWeight: 600, color: '#111827' }}>
                        NT$ {Math.round(item.unit_price * item.quantity * receipt_info.exchange_rate)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          
          <div style={{ height: '400px' }}>
             <h3 className="card-title" style={{ fontSize: '1.2rem', marginBottom: '1rem', textAlign: 'center' }}>📊 支出比例</h3>
             <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={chartData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={5} dataKey="value">
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => `NT$ ${value}`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>AI 智能發票系統</h1>
        <p>上傳多國發票，AI 自動翻譯品項、抓取匯率並完成記帳分析。</p>
      </header>

      <div className="main-grid">
        {/* Sidebar settings */}
        <div className="glass-card">
          <h2 className="card-title">系統設定</h2>
          
          <div className="form-group">
            <label className="form-label">大語言模型</label>
            <select className="form-select" value={provider} onChange={e => setProvider(e.target.value)}>
              <option value="Gemini">Google Gemini</option>
              <option value="OpenAI">OpenAI GPT</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">API Key</label>
            <input 
              type="password" 
              className="form-input" 
              placeholder={`輸入您的 ${provider} API 金鑰`}
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">影像主要語系</label>
            <select className="form-select" value={ocrLang} onChange={e => setOcrLang(e.target.value)}>
              <option value="ch">繁體中文</option>
              <option value="japan">日文</option>
              <option value="korean">韓文</option>
              <option value="en">英文</option>
            </select>
          </div>
        </div>

        {/* Main Content */}
        <div className="glass-card">
          <h2 className="card-title">上傳發票</h2>
          
          <div 
            className="upload-area" 
            onDragOver={handleDragOver} 
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadCloud className="upload-icon" />
            <div>
              <p style={{ fontWeight: 600, fontSize: '1.1rem' }}>點擊選擇圖片，或將圖片拖曳至此</p>
              <p style={{ color: '#6B7280', fontSize: '0.9rem', marginTop: '0.5rem' }}>支援 JPG, PNG 格式</p>
            </div>
            <input 
              type="file" 
              style={{ display: 'none' }} 
              ref={fileInputRef} 
              accept="image/*"
              onChange={(e) => setFile(e.target.files[0])}
            />
          </div>
          
          {file && (
            <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#F3F4F6', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CheckCircle size={20} color="#10B981" />
              <span style={{ fontWeight: 500 }}>已選擇檔案: {file.name}</span>
            </div>
          )}

          {error && (
            <div className="error-message">
              <AlertCircle size={20} />
              <span>{error}</span>
            </div>
          )}

          <button 
            className="btn-primary" 
            onClick={processInvoice}
            disabled={isProcessing || !file}
          >
            {isProcessing ? (
              <><Loader2 className="spinner" /> AI 處理與解析中，請稍候...</>
            ) : (
              <><RefreshCw size={20} /> 開始全自動解析</>
            )}
          </button>
        </div>
        
        {renderDashboard()}
      </div>
    </div>
  );
}

export default App;
