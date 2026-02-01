#!/usr/bin/env python3
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import re
import base64
import json
from urllib.parse import unquote
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Simple HTTP server for Railway health checks
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass

def start_http_server():
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ HTTP server running on port {port}")
    server.serve_forever()

# Start HTTP server in background thread
http_thread = threading.Thread(target=start_http_server, daemon=True)
http_thread.start()

class PDFEmbedderExtractor:
    @staticmethod
    def extract_pdf_from_page(url: str) -> dict:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return {'success': False, 'pdf_url': None, 'details': f"HTTP {response.status_code}"}
            
            html = response.text
            
            # Method 1: Look for pdfemb-data in iframes
            iframe_pattern = r'<iframe[^>]*src="([^"]*pdfemb-data[^"]*)"'
            iframe_matches = re.findall(iframe_pattern, html, re.IGNORECASE)
            
            for iframe_src in iframe_matches:
                param_pattern = r'pdfemb-data=([^&"\']+)'
                param_match = re.search(param_pattern, iframe_src)
                
                if param_match:
                    base64_data = param_match.group(1)
                    pdf_url = PDFEmbedderExtractor._decode_pdfemb_data(base64_data)
                    if pdf_url:
                        return {'success': True, 'pdf_url': pdf_url, 'method': 'iframe'}
            
            # Method 2: Direct pdfemb-data
            direct_pattern = r'pdfemb-data[=:]["\']([^"\']+)["\']'
            direct_matches = re.findall(direct_pattern, html)
            
            for base64_data in direct_matches:
                pdf_url = PDFEmbedderExtractor._decode_pdfemb_data(base64_data)
                if pdf_url:
                    return {'success': True, 'pdf_url': pdf_url, 'method': 'direct'}
            
            return {'success': False, 'pdf_url': None, 'details': 'Not found'}
                
        except Exception as e:
            return {'success': False, 'pdf_url': None, 'details': str(e)}
    
    @staticmethod
    def _decode_pdfemb_data(base64_str: str) -> str:
        try:
            base64_str = base64_str.strip()
            padding = 4 - len(base64_str) % 4
            if padding != 4:
                base64_str += '=' * padding
            
            decoded_bytes = base64.b64decode(base64_str)
            decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
            
            if '{' in decoded_str and '}' in decoded_str:
                try:
                    data = json.loads(decoded_str)
                    if 'pdfemb-serverurl' in data:
                        return unquote(data['pdfemb-serverurl'])
                    for key, value in data.items():
                        if isinstance(value, str) and '.pdf' in value.lower():
                            return unquote(value)
                except:
                    pass
            
            patterns = [r'https?%3A%2F%2F[^"\']+\.pdf', r'https?://[^\s"\']+\.pdf']
            for pattern in patterns:
                match = re.search(pattern, decoded_str, re.IGNORECASE)
                if match:
                    pdf_url = match.group(0)
                    if '%' in pdf_url:
                        pdf_url = unquote(pdf_url)
                    return pdf_url
            
            return None
        except:
            return None
    
    @staticmethod
    def download_pdf(pdf_url: str) -> tuple:
        try:
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.elearning-cpge.com/'}
            response = requests.get(pdf_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                content = response.content
                if len(content) > 4 and content[:4] == b'%PDF':
                    return True, content, "Success"
                elif 'pdf' in response.headers.get('Content-Type', '').lower():
                    return True, content, "Success"
            return False, None, f"HTTP {response.status_code}"
        except Exception as e:
            return False, None, str(e)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salaaam, m3ak Hiba, kan9d nkhrj lik PDF mn ay link dyal elearning-cpge.com.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    
    if user_input.startswith('/'):
        return
    
    if 'elearning-cpge.com' not in user_input:
        await update.message.reply_text("WA TA SIFT LIEN D ELEARNING M9AD!!")
        return
    
    wait_msg = await update.message.reply_text("Sbeeeeeer...")
    
    try:
        await wait_msg.edit_text("Bchwiya 3linaaa...")
        extractor = PDFEmbedderExtractor()
        result = extractor.extract_pdf_from_page(user_input)
        
        if result['success'] and result['pdf_url']:
            await wait_msg.edit_text("Hani b3da l9ito hehehe...")
            success, pdf_content, message = extractor.download_pdf(result['pdf_url'])
            
            if success and pdf_content:
                filename = result['pdf_url'].split('/')[-1] or "document.pdf"
                filename = re.sub(r'[^\w\.-]', '_', filename)
                if not filename.lower().endswith('.pdf'):
                    filename += '.pdf'
                
                await update.message.reply_document(
                    document=pdf_content,
                    filename=filename,
                    caption="3la slamti hahwak pdf dyalk litlbti. U r welcome!"
                )
                await wait_msg.delete()
            else:
                await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
        else:
            await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
    except Exception as e:
        await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN not set")
        return
    
    print("🚀 Starting bot...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()
