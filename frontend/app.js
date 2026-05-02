// app.js - Nexus Quant Frontend Logic

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initPresets();
    initBacktestEngine();
    initAccountEngine();
    initLiveBotEngine();
});

// --- Tab Navigation ---
function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const tabTitle = document.getElementById('current-tab-title');
    const tabDesc = document.getElementById('current-tab-desc');

    const titles = {
        'config': { title: '策略参数配置', desc: '调整 v4.0 用户策略模型核心参数' },
        'logs': { title: '运行日志', desc: '终端输出与实时回测进度' },
        'results': { title: '回测报告', desc: '交互式可视化分析与统计数据' },
        'account': { title: 'API与账户', desc: '统一账户资金、持仓查询与 API 密钥管理' },
        'live': { title: '实盘量化引擎', desc: '自动化交易机器人监控与紧急接管' }
    };

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = item.getAttribute('data-tab');
            
            // Switch active nav item
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');

            // Switch active tab pane
            tabPanes.forEach(pane => pane.classList.remove('active'));
            document.getElementById(`pane-${targetId}`).classList.add('active');

            // Update Header
            tabTitle.textContent = titles[targetId].title;
            tabDesc.textContent = titles[targetId].desc;

            // Resize charts if switching to results
            if(targetId === 'results') {
                setTimeout(resizeCharts, 100);
            }
        });
    });
}

// --- Presets Management ---
function initPresets() {
    const presets = document.querySelectorAll('.preset-btn:not(.add-preset)');
    presets.forEach(preset => {
        preset.addEventListener('click', () => {
            presets.forEach(p => p.classList.remove('active'));
            preset.classList.add('active');
            
            // Highlight a quick animation on form
            const form = document.getElementById('config-form');
            form.style.opacity = '0.5';
            setTimeout(() => form.style.opacity = '1', 200);
            
            // Here you would load specific JSON into the form
        });
    });
}

// --- Backtest Engine Simulation ---
let chartsInitialized = false;
let chartEquity, chartMonthly, chartPnl;

function initBacktestEngine() {
    const btnRun = document.getElementById('btn-run-backtest');
    
    btnRun.addEventListener('click', () => {
        // Switch to Logs Tab automatically
        document.querySelector('[data-tab="logs"]').click();
        
        startMockBacktest();
    });
}

function startMockBacktest() {
    const consoleOutput = document.getElementById('console-output');
    const statusIndicator = document.getElementById('console-status-indicator');
    const progressContainer = document.getElementById('progress-container');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const progressStats = document.getElementById('progress-stats');
    const btnRun = document.getElementById('btn-run-backtest');

    // Reset UI
    consoleOutput.innerHTML = '';
    progressContainer.style.display = 'block';
    progressFill.style.width = '0%';
    statusIndicator.className = 'console-status status-running';
    statusIndicator.textContent = '● RUNNING';
    btnRun.disabled = true;
    btnRun.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 回测中...';

    const appendLog = (text, className = '') => {
        const div = document.createElement('div');
        div.className = `log-line ${className}`;
        div.textContent = text;
        consoleOutput.appendChild(div);
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    };

    // Configuration from form
    const formData = new FormData(document.getElementById('config-form'));
    const symbol = formData.get('symbols') || 'ETH/USDT';
    
    // Initial logs
    appendLog(`[SYSTEM] Initializing Backtest Engine v4.0...`, 'sys-msg');
    setTimeout(() => appendLog(`[CONFIG] Loading symbol: ${symbol}`, 'sys-msg'), 500);
    setTimeout(() => appendLog(`[CONFIG] Timeframe: ${formData.get('start_date')} to ${formData.get('end_date')}`, 'sys-msg'), 800);
    setTimeout(() => appendLog(`[DATA] Fetching 1d, 4h, 1h OHLCV from Binance...`, 'sys-msg'), 1200);
    setTimeout(() => appendLog(`  ↓ ${symbol} [1d  ] 1,460 条  ✓`, 'success'), 2000);
    setTimeout(() => appendLog(`  ↓ ${symbol} [4h  ] 8,760 条  ✓`, 'success'), 2400);
    setTimeout(() => appendLog(`  ↓ ${symbol} [1h  ] 35,040 条  ✓`, 'success'), 2900);
    setTimeout(() => appendLog(`[ENGINE] Data prepared. Starting step simulation...`, 'highlight'), 3400);

    // Simulation loop
    let progress = 0;
    let cap = 10000;
    let trades = 0;
    let mdd = 0;

    setTimeout(() => {
        const interval = setInterval(() => {
            progress += Math.random() * 5;
            if(progress >= 100) progress = 100;
            
            // Randomly update stats
            if(Math.random() > 0.6) trades++;
            if(Math.random() > 0.5) cap += (Math.random() * 100 - 45); // slight upward bias
            if(cap < 10000) mdd = Math.max(mdd, (10000 - cap)/10000);

            // Update UI
            progressFill.style.width = `${progress}%`;
            progressText.textContent = `进度: ${progress.toFixed(1)}%`;
            progressStats.textContent = `资金: ${cap.toFixed(2)} U | 交易: ${trades}笔 | 回撤: ${(mdd*100).toFixed(1)}%`;

            // Randomly print log
            if(Math.random() > 0.8) {
                const isLong = Math.random() > 0.5;
                const pnl = Math.random() > 0.6 ? (Math.random()*200) : -(Math.random()*150);
                const action = isLong ? 'LONG ' : 'SHORT';
                const resClass = pnl > 0 ? 'success' : 'error';
                appendLog(`[TRADE] ${action} Closed. PnL: ${pnl > 0 ? '+' : ''}${pnl.toFixed(2)} USDT`, resClass);
            }

            if(progress === 100) {
                clearInterval(interval);
                finishBacktest(cap, trades, mdd);
            }
        }, 150);
    }, 3600);

    function finishBacktest(finalCap, totalTrades, finalMdd) {
        appendLog(`[ENGINE] Backtest complete.`, 'highlight');
        appendLog(`[STATS] Final Capital: ${finalCap.toFixed(2)} USDT | Total Trades: ${totalTrades}`, 'sys-msg');
        
        statusIndicator.className = 'console-status status-done';
        statusIndicator.textContent = '● DONE';
        btnRun.disabled = false;
        btnRun.innerHTML = '<i class="fa-solid fa-play"></i> 重新回测';
        
        // Render Charts and navigate
        setTimeout(() => {
            document.querySelector('[data-tab="results"]').click();
            renderResultsDashboard(finalCap, totalTrades, finalMdd);
        }, 1500);
    }
}

// --- ECharts Visualization ---
function renderResultsDashboard(finalCap, totalTrades, finalMdd) {
    const initCap = parseFloat(document.querySelector('input[name="initial_capital"]').value) || 10000;
    const roi = (finalCap - initCap) / initCap;
    
    // Update Stat Cards
    const elRoi = document.getElementById('res-roi');
    elRoi.textContent = `${roi > 0 ? '+' : ''}${(roi*100).toFixed(2)}%`;
    elRoi.className = `stat-value ${roi >= 0 ? 'positive' : 'negative'}`;
    
    document.getElementById('res-final-cap').textContent = `${finalCap.toFixed(2)} U`;
    document.getElementById('res-win-rate').textContent = '62.4%'; // Mock
    
    const elMdd = document.getElementById('res-mdd');
    elMdd.textContent = `${(finalMdd*100).toFixed(1)}%`;
    
    document.getElementById('res-sharpe').textContent = '1.85'; // Mock
    document.getElementById('res-trades').textContent = totalTrades.toString();

    // Init ECharts if not already
    if(!chartsInitialized) {
        chartEquity = echarts.init(document.getElementById('chart-equity'));
        chartMonthly = echarts.init(document.getElementById('chart-monthly'));
        chartPnl = echarts.init(document.getElementById('chart-pnl'));
        chartsInitialized = true;
    }

    // Colors
    const cPrimary = '#00FF88';
    const cDanger = '#FF3366';
    const cText = '#94A3B8';
    const cBorder = '#2A3241';

    // Mock Equity Curve Data
    let eqData = [initCap];
    let dates = ['2022-01'];
    let curr = initCap;
    for(let i=1; i<100; i++) {
        curr += (Math.random() * 400 - 150);
        eqData.push(curr);
        dates.push(`Day ${i}`);
    }

    chartEquity.setOption({
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(21,26,34,0.9)', borderColor: cBorder, textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: dates, axisLine: { lineStyle: { color: cBorder } }, axisLabel: { color: cText } },
        yAxis: { type: 'value', min: 'dataMin', axisLine: { show: false }, splitLine: { lineStyle: { color: cBorder, type: 'dashed' } }, axisLabel: { color: cText } },
        series: [
            {
                name: 'Capital',
                type: 'line',
                data: eqData,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#00A3FF' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(0,163,255,0.3)' },
                        { offset: 1, color: 'rgba(0,163,255,0)' }
                    ])
                }
            }
        ]
    });

    // Mock Monthly Return Data
    chartMonthly.setOption({
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(21,26,34,0.9)', borderColor: cBorder, textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'], axisLine: { lineStyle: { color: cBorder } }, axisLabel: { color: cText } },
        yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: cBorder, type: 'dashed' } }, axisLabel: { color: cText } },
        series: [
            {
                name: 'PnL',
                type: 'bar',
                data: [120, 200, -150, 80, 70, 300, -50, 420],
                itemStyle: {
                    borderRadius: [4, 4, 0, 0],
                    color: function(params) {
                        return params.value > 0 ? cPrimary : cDanger;
                    }
                }
            }
        ]
    });

    // Mock PnL Ratio Data
    chartPnl.setOption({
        tooltip: { trigger: 'item', backgroundColor: 'rgba(21,26,34,0.9)', borderColor: cBorder, textStyle: { color: '#fff' } },
        legend: { top: '5%', left: 'center', textStyle: { color: cText } },
        series: [
            {
                name: 'Trades',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: '#151A22',
                    borderWidth: 2
                },
                label: { show: false, position: 'center' },
                emphasis: {
                    label: { show: true, fontSize: 20, fontWeight: 'bold', color: '#fff' }
                },
                labelLine: { show: false },
                data: [
                    { value: totalTrades * 0.62, name: 'Wins', itemStyle: { color: cPrimary } },
                    { value: totalTrades * 0.38, name: 'Losses', itemStyle: { color: cDanger } }
                ]
            }
        ]
    });
}

function resizeCharts() {
    if(chartsInitialized) {
        chartEquity.resize();
        chartMonthly.resize();
        chartPnl.resize();
    }
}

window.addEventListener('resize', resizeCharts);

// --- API Keys Sync ---
async function syncApiKeys() {
    const apiKey = document.querySelector('input[name="api_key"]').value;
    const secretKey = document.querySelector('input[name="secret_key"]').value;
    await fetch('/api/config/keys', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({api_key: apiKey, secret_key: secretKey})
    });
}

// --- Account Info API Integration ---
function initAccountEngine() {
    const btn = document.getElementById('btn-fetch-account');
    if(!btn) return;
    btn.addEventListener('click', async () => {
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 加载中...';
        btn.disabled = true;
        
        try {
            await syncApiKeys();
            const res = await fetch('/api/account/snapshot');
            const result = await res.json();
            
            if(result.status === 'success') {
                renderAccountSnapshot(result.data);
            } else {
                alert('获取快照失败: ' + result.detail);
            }
        } catch(e) {
            alert('网络错误: ' + e);
        } finally {
            btn.innerHTML = '<i class="fa-solid fa-rotate"></i> 刷新快照';
            btn.disabled = false;
        }
    });
}

function renderAccountSnapshot(data) {
    // Expected data structure from AccountSnapshot.full_snapshot()
    const overview = data.overview || {};
    const positions = data.positions || [];

    const accountOverview = document.getElementById('account-overview');
    accountOverview.innerHTML = `
        <div class="stats-grid" style="margin-bottom: 0; width: 100%;">
            <div class="stat-card">
                <div class="stat-title">账户总权益 (USD)</div>
                <div class="stat-value" style="font-size: 20px;">${parseFloat(overview.totalEquity || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">统一保证金比例 (uniMMR)</div>
                <div class="stat-value ${parseFloat(overview.uniMMR) > 100 ? 'negative' : 'positive'}" style="font-size: 20px;">${(parseFloat(overview.uniMMR || 0) * 100).toFixed(2)}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">维持保证金</div>
                <div class="stat-value" style="font-size: 20px;">${parseFloat(overview.totalMaintMargin || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">可用余额</div>
                <div class="stat-value" style="font-size: 20px;">${parseFloat(overview.accountEquity || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}</div>
            </div>
        </div>
    `;

    const tbody = document.getElementById('positions-tbody');
    tbody.innerHTML = '';
    
    if (positions.length === 0) {
         tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px 0;">当前无活动持仓</td></tr>';
         return;
    }

    positions.forEach(pos => {
        const amt = parseFloat(pos.positionAmt);
        if (amt === 0) return;
        
        const sideClass = amt > 0 ? 'pos-long' : 'pos-short';
        const sideText = amt > 0 ? 'LONG ▲' : 'SHORT ▼';
        const upnl = parseFloat(pos.unrealizedProfit);
        const pnlClass = upnl >= 0 ? 'positive' : 'negative';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${pos.symbol}</strong></td>
            <td class="${sideClass}">${sideText}</td>
            <td>${pos.leverage}x</td>
            <td>${Math.abs(amt)}</td>
            <td>${parseFloat(pos.entryPrice).toFixed(2)}</td>
            <td>${parseFloat(pos.markPrice).toFixed(2)}</td>
            <td class="stat-value ${pnlClass}" style="font-size: 14px;">${upnl > 0 ? '+' : ''}${upnl.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// --- Live Trading Bot Engine Integration (WebSocket) ---
function initLiveBotEngine() {
    const btnToggle = document.getElementById('btn-toggle-bot');
    const dot = document.getElementById('live-bot-dot');
    const status = document.getElementById('live-bot-status');
    const sigDaily = document.getElementById('sig-daily');
    const sig4h = document.getElementById('sig-4h');
    const sigDist = document.getElementById('sig-dist');
    const sigAdx = document.getElementById('sig-adx');
    const logContainer = document.getElementById('signal-log-container');
    const execTbody = document.getElementById('live-execution-tbody');
    const liveSymbolSelect = document.getElementById('live-symbol');
    
    if(!btnToggle) return;

    let isRunning = false;
    let ws = null;

    btnToggle.addEventListener('click', () => {
        isRunning = !isRunning;
        if(isRunning) {
            btnToggle.innerHTML = '<i class="fa-solid fa-stop"></i> 停止机器人';
            btnToggle.classList.remove('btn-primary');
            btnToggle.classList.add('btn-secondary');
            btnToggle.style.borderColor = 'var(--danger)';
            btnToggle.style.color = 'var(--danger)';
            
            dot.style.background = 'var(--primary)';
            dot.style.boxShadow = '0 0 10px var(--primary)';
            status.textContent = '运行中 - 监听信号';
            status.style.color = 'var(--primary)';
            
            logContainer.innerHTML = '<div class="log-line sys-msg">[SYSTEM] 正在连接后端实盘引擎 WebSocket...</div>';
            syncApiKeys().then(() => {
                startLiveBotWS();
            });
        } else {
            btnToggle.innerHTML = '<i class="fa-solid fa-play"></i> 启动实盘机器人';
            btnToggle.classList.remove('btn-secondary');
            btnToggle.classList.add('btn-primary');
            btnToggle.style.borderColor = 'transparent';
            btnToggle.style.color = 'var(--bg-main)';
            
            dot.style.background = 'var(--text-muted)';
            dot.style.boxShadow = 'none';
            status.textContent = '系统离线 - 待启动';
            status.style.color = 'var(--text-muted)';
            
            if (ws) {
                ws.send(JSON.stringify({ action: 'stop' }));
                ws.close();
            }
            sigDaily.textContent = '--'; sigDaily.style.color = '';
            sig4h.textContent = '--'; sig4h.style.color = '';
            sigDist.textContent = '--'; sigDist.style.color = '';
            sigAdx.textContent = '--'; sigAdx.style.color = '';
            logContainer.innerHTML += '<div class="log-line sys-msg">[SYSTEM] 机器人已安全停止，WebSocket 断开。</div>';
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    });

    function startLiveBotWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws/bot`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            logContainer.innerHTML += '<div class="log-line sys-msg">[SYSTEM] WebSocket 连接成功。请求启动引擎...</div>';
            ws.send(JSON.stringify({
                action: 'start',
                symbol: liveSymbolSelect.value
            }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'log') {
                    appendLog(data.message, data.level);
                } else if (data.type === 'signal_update') {
                    updateRadar(data);
                } else if (data.type === 'execution') {
                    appendExecution(data);
                }
            } catch(e) {
                console.error("Failed to parse WS message", event.data);
            }
        };

        ws.onerror = (error) => {
            appendLog('[ERROR] WebSocket 发生错误', 'error');
        };

        ws.onclose = () => {
            if (isRunning) {
                appendLog('[ERROR] WebSocket 意外断开', 'error');
                // Automatically toggle button off
                btnToggle.click();
            }
        };
    }

    function appendLog(message, level) {
        const now = new Date().toLocaleTimeString();
        const logMsg = document.createElement('div');
        logMsg.className = 'log-line';
        if (level) logMsg.classList.add(level);
        
        let displayMsg = message;
        if (!message.startsWith('[SYSTEM]') && !message.startsWith('[ERROR]')) {
             displayMsg = `<span style="color:#8b949e">[${now}]</span> ${message}`;
        }
        logMsg.innerHTML = displayMsg;
        logContainer.appendChild(logMsg);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function updateRadar(data) {
        if(data.daily) {
            sigDaily.textContent = data.daily.text;
            sigDaily.style.color = data.daily.color;
        }
        if(data.h4) {
            sig4h.textContent = data.h4.text;
            sig4h.style.color = data.h4.color;
        }
        if(data.dist) {
            sigDist.textContent = data.dist.text;
            sigDist.style.color = data.dist.color;
        }
        if(data.adx) {
            sigAdx.textContent = data.adx.text;
            sigAdx.style.color = data.adx.color;
        }
    }

    function appendExecution(data) {
        if(execTbody.innerHTML.includes('暂无订单执行记录')) {
            execTbody.innerHTML = '';
        }
        const now = new Date().toLocaleTimeString();
        const actionStr = data.side === 'BUY' && data.posSide === 'LONG' ? '开多 ▲' : 
                          data.side === 'SELL' && data.posSide === 'SHORT' ? '开空 ▼' : 
                          data.side === 'SELL' && data.posSide === 'LONG' ? '平多 ▼' : '平空 ▲';
        
        const actionClass = data.side === 'BUY' ? 'pos-long' : 'pos-short';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${now}</td>
            <td class="${actionClass}">${actionStr}</td>
            <td>${data.orderType}</td>
            <td>${data.qty}</td>
            <td>${data.price.toFixed(2)}</td>
            <td><span style="background:rgba(0,255,136,0.1); color:var(--primary); padding:2px 6px; border-radius:4px; font-size:10px; border:1px solid rgba(0,255,136,0.3)">FILLED</span></td>
            <td style="font-family:var(--font-mono); color:var(--text-muted); font-size: 11px;">${data.orderId}</td>
        `;
        execTbody.insertBefore(tr, execTbody.firstChild);
    }



    // --- Manual Trade API Integration ---
    const btnLong = document.getElementById('btn-manual-long');
    const btnShort = document.getElementById('btn-manual-short');
    const btnPanic = document.getElementById('btn-manual-panic');
    
    if(btnPanic) {
        btnPanic.addEventListener('click', async () => {
            if(!confirm('🚨 确定要紧急撤销所有挂单并市价平仓吗？')) return;
            const symbol = liveSymbolSelect.value;
            try {
                await syncApiKeys();
                const res = await fetch('/api/trade/panic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ symbol: symbol })
                });
                const result = await res.json();
                if(result.status === 'success') {
                    alert('一键平仓执行成功！已平仓数量: ' + result.closed_positions.length);
                    document.getElementById('btn-fetch-account')?.click();
                } else {
                    alert('平仓失败: ' + result.detail);
                }
            } catch(e) {
                alert('网络错误: ' + e);
            }
        });
    }

    if(btnLong) {
        btnLong.addEventListener('click', async () => {
            const qty = prompt("请输入市价开多数量 (例如 0.01):", "0.01");
            if(!qty) return;
            const symbol = liveSymbolSelect.value;
            try {
                await syncApiKeys();
                const res = await fetch('/api/trade/market', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ symbol: symbol, side: 'BUY', position_side: 'LONG', quantity: parseFloat(qty) })
                });
                const result = await res.json();
                if(result.status === 'success') {
                    alert('市价开多成功！OrderID: ' + result.data.orderId);
                    document.getElementById('btn-fetch-account')?.click();
                } else {
                    alert('开单失败: ' + result.detail);
                }
            } catch(e) {
                alert('网络错误: ' + e);
            }
        });
    }

    if(btnShort) {
        btnShort.addEventListener('click', async () => {
            const qty = prompt("请输入市价开空数量 (例如 0.01):", "0.01");
            if(!qty) return;
            const symbol = liveSymbolSelect.value;
            try {
                await syncApiKeys();
                const res = await fetch('/api/trade/market', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ symbol: symbol, side: 'SELL', position_side: 'SHORT', quantity: parseFloat(qty) })
                });
                const result = await res.json();
                if(result.status === 'success') {
                    alert('市价开空成功！OrderID: ' + result.data.orderId);
                    document.getElementById('btn-fetch-account')?.click();
                } else {
                    alert('开单失败: ' + result.detail);
                }
            } catch(e) {
                alert('网络错误: ' + e);
            }
        });
    }
}

