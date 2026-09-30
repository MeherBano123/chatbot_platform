/**
 * Embeddable Chatbot Widget - Fixed Version
 * Displays FAQs from scraped website data
 */
(function() {
    'use strict';
    
    // Configuration
    var websiteId = document.currentScript.getAttribute('data-website-id');
    var apiUrl = document.currentScript.getAttribute('data-api-url') || 'http://localhost:5000';
    
    console.log(' Chatbot initializing...', { websiteId, apiUrl });
    
    if (!websiteId) {
        console.error(' Chatbot Error: data-website-id attribute is required');
        return;
    }
    
    var faqs = [];
    var expandedFaqs = {};
    
    // Create chatbot HTML
    var chatbotHTML = `
        <div id="chatbot-widget" style="position: fixed; bottom: 20px; right: 20px; z-index: 9999; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <button id="chatbot-toggle" style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 50%;
                width: 60px;
                height: 60px;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
                font-size: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: transform 0.2s, box-shadow 0.2s;
            " onmouseover="this.style.transform='scale(1.1)'; this.style.boxShadow='0 6px 16px rgba(102, 126, 234, 0.6)';" 
               onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='0 4px 12px rgba(102, 126, 234, 0.4)';">
                💬
            </button>
            
            <div id="chatbot-window" style="
                display: none;
                position: fixed;
                bottom: 90px;
                right: 20px;
                width: 380px;
                max-width: calc(100vw - 40px);
                height: 550px;
                max-height: calc(100vh - 120px);
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                flex-direction: column;
                overflow: hidden;
                animation: slideIn 0.3s ease-out;
            ">
                <!-- Header -->
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 18px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                ">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="
                            width: 36px;
                            height: 36px;
                            background: rgba(255,255,255,0.2);
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 18px;
                        ">💬</div>
                        <div>
                            <div style="font-weight: 600; font-size: 16px;">FAQ Assistant</div>
                            <div id="chatbot-status" style="font-size: 12px; opacity: 0.9;">Loading...</div>
                        </div>
                    </div>
                    <button id="chatbot-close" style="
                        background: transparent;
                        border: none;
                        color: white;
                        font-size: 24px;
                        cursor: pointer;
                        width: 32px;
                        height: 32px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: background 0.2s;
                    " onmouseover="this.style.background='rgba(255,255,255,0.2)';" 
                       onmouseout="this.style.background='transparent';">
                        ×
                    </button>
                </div>
                
                <!-- Messages Container -->
                <div id="chatbot-messages" style="
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                    background: #f8f9fa;
                "></div>
                
                <!-- Footer -->
                <div style="
                    padding: 12px 20px;
                    background: white;
                    border-top: 1px solid #e5e7eb;
                    font-size: 11px;
                    color: #9ca3af;
                    text-align: center;
                ">
                    Powered by AI Web Scraper
                </div>
            </div>
        </div>
        
        <style>
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            #chatbot-messages::-webkit-scrollbar {
                width: 6px;
            }
            
            #chatbot-messages::-webkit-scrollbar-track {
                background: #f1f1f1;
            }
            
            #chatbot-messages::-webkit-scrollbar-thumb {
                background: #888;
                border-radius: 3px;
            }
            
            #chatbot-messages::-webkit-scrollbar-thumb:hover {
                background: #555;
            }
        </style>
    `;
    
    // Inject chatbot into page
    document.body.insertAdjacentHTML('beforeend', chatbotHTML);
    
    // Get elements
    var toggle = document.getElementById('chatbot-toggle');
    var chatWindow = document.getElementById('chatbot-window');
    var closeBtn = document.getElementById('chatbot-close');
    var messages = document.getElementById('chatbot-messages');
    var statusEl = document.getElementById('chatbot-status');
    
    /**
     * Update status message
     */
    function updateStatus(text) {
        if (statusEl) {
            statusEl.textContent = text;
        }
    }
    
    /**
     * Show loading state
     */
    function showLoading() {
        messages.innerHTML = `
            <div style="
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: #6b7280;
            ">
                <div style="
                    width: 50px;
                    height: 50px;
                    border: 4px solid #e5e7eb;
                    border-top-color: #667eea;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                "></div>
                <p style="margin-top: 16px; font-size: 14px;">Loading FAQs...</p>
            </div>
            <style>
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            </style>
        `;
        updateStatus('Loading...');
    }
    
    /**
     * Show error message
     */
    function showError(message) {
        messages.innerHTML = `
            <div style="
                text-align: center;
                padding: 40px 20px;
                color: #ef4444;
            ">
                <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                <p style="font-weight: 600; font-size: 16px; margin-bottom: 8px;">Error Loading FAQs</p>
                <p style="font-size: 14px; color: #9ca3af;">${message}</p>
            </div>
        `;
        updateStatus('Error');
    }
    
    /**
     * Show empty state
     */
    function showEmptyState() {
        messages.innerHTML = `
            <div style="
                text-align: center;
                padding: 40px 20px;
                color: #6b7280;
            ">
                <div style="font-size: 64px; margin-bottom: 16px;">💬</div>
                <p style="font-weight: 600; color: #374151; font-size: 18px; margin-bottom: 8px;">
                    Hello! How can I help you?
                </p>
                <p style="font-size: 14px; margin-top: 8px; color: #9ca3af;">
                    No FAQs available yet. We're still scraping the website.
                </p>
                <button onclick="location.reload()" style="
                    margin-top: 16px;
                    padding: 10px 20px;
                    background: #667eea;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                ">
                    Refresh
                </button>
            </div>
        `;
        updateStatus('No FAQs yet');
    }
    
    /**
     * Show FAQs
     */
    function showFAQs() {
        if (!faqs || faqs.length === 0) {
            showEmptyState();
            return;
        }
        
        var faqHTML = `
            <div style="margin-bottom: 20px;">
                <div style="
                    text-align: center;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #e5e7eb;
                ">
                    <div style="font-size: 48px; margin-bottom: 12px;">💬</div>
                    <p style="font-weight: 600; color: #374151; font-size: 18px; margin-bottom: 4px;">
                        Frequently Asked Questions
                    </p>
                    <p style="font-size: 13px; color: #6b7280;">
                        Click any question to see the answer
                    </p>
                </div>
            </div>
            
            <div style="margin-top: 20px;">
                <p style="
                    font-size: 11px;
                    font-weight: 700;
                    color: #9ca3af;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    margin-bottom: 12px;
                ">
                    ${faqs.length} Question${faqs.length !== 1 ? 's' : ''} Available
                </p>
        `;
        
        faqs.forEach(function(faq, idx) {
            var isExpanded = expandedFaqs[idx] || false;
            
            faqHTML += `
                <div style="
                    margin-bottom: 10px;
                    border: 1px solid ${isExpanded ? '#667eea' : '#e5e7eb'};
                    border-radius: 12px;
                    overflow: hidden;
                    transition: all 0.3s ease;
                    background: ${isExpanded ? '#f0f4ff' : 'white'};
                    box-shadow: ${isExpanded ? '0 4px 12px rgba(102, 126, 234, 0.15)' : '0 2px 4px rgba(0,0,0,0.05)'};
                ">
                    <button 
                        class="faq-question-btn"
                        data-index="${idx}"
                        style="
                            width: 100%;
                            text-align: left;
                            padding: 16px;
                            background: transparent;
                            border: none;
                            cursor: pointer;
                            font-size: 14px;
                            color: #1f2937;
                            font-weight: 500;
                            display: flex;
                            justify-content: space-between;
                            align-items: flex-start;
                            gap: 12px;
                        "
                    >
                        <span style="flex: 1; line-height: 1.5;">${faq.question}</span>
                        <span style="
                            font-size: 18px;
                            color: #667eea;
                            transition: transform 0.3s ease;
                            transform: rotate(${isExpanded ? '180deg' : '0deg'});
                            flex-shrink: 0;
                        ">▼</span>
                    </button>
                    
                    <div style="
                        max-height: ${isExpanded ? '1000px' : '0'};
                        overflow: hidden;
                        transition: max-height 0.3s ease;
                    ">
                        <div style="
                            padding: ${isExpanded ? '0 16px 16px 16px' : '0 16px'};
                            color: #4b5563;
                            font-size: 14px;
                            line-height: 1.6;
                            background: white;
                            border-top: ${isExpanded ? '1px solid #e5e7eb' : 'none'};
                        ">
                            ${faq.answer}
                        </div>
                    </div>
                </div>
            `;
        });
        
        faqHTML += '</div>';
        
        messages.innerHTML = faqHTML;
        updateStatus(`${faqs.length} FAQs available`);
        
        // Add click handlers
        var faqButtons = messages.querySelectorAll('.faq-question-btn');
        faqButtons.forEach(function(btn) {
            btn.onclick = function(e) {
                e.preventDefault();
                var idx = parseInt(this.getAttribute('data-index'));
                toggleFaq(idx);
            };
        });
    }
    
    /**
     * Toggle FAQ expansion
     */
    function toggleFaq(index) {
        expandedFaqs[index] = !expandedFaqs[index];
        showFAQs();
    }
    
    /**
     * Load FAQs from API
     */
    function loadFaqs() {
        console.log('📡 Fetching FAQs for website:', websiteId);
        showLoading();
        
        var url = apiUrl + '/api/faqs/' + websiteId;
        console.log('🌐 API URL:', url);
        
        fetch(url)
            .then(function(response) {
                console.log('📥 Response status:', response.status);
                
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status + ': ' + response.statusText);
                }
                
                return response.json();
            })
            .then(function(data) {
                console.log('✅ FAQs received:', data);
                
                // Store FAQs
                faqs = data;
                
                // Display
                showFAQs();
            })
            .catch(function(error) {
                console.error('❌ Error loading FAQs:', error);
                showError(error.message || 'Failed to load FAQs. Please try again later.');
            });
    }
    
    /**
     * Toggle chatbot visibility
     */
    toggle.onclick = function() {
        var isHidden = chatWindow.style.display === 'none';
        chatWindow.style.display = isHidden ? 'flex' : 'none';
        
        // Load FAQs when opening for first time
        if (isHidden && faqs.length === 0) {
            loadFaqs();
        }
    };
    
    /**
     * Close chatbot
     */
    closeBtn.onclick = function() {
        chatWindow.style.display = 'none';
    };
    
    // Auto-load FAQs after 2 seconds (optional)
    setTimeout(function() {
        if (faqs.length === 0) {
            console.log('🔄 Auto-loading FAQs...');
            loadFaqs();
        }
    }, 2000);
    
    console.log('✅ Chatbot widget initialized successfully');
})();