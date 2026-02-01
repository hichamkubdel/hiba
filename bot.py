#!/usr/bin/env python3
import asyncio
import requests
import re
import base64
import json
import logging
import os
import sys
import threading
from aiohttp import web
from urllib.parse import unquote
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PDFEmbedderExtractor:
    @staticmethod
    def extract_pdf_from_page(url: str) -> dict:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'pdf_url': None,
                    'method': 'Erreur HTTP',
                    'details': f"HTTP {response.status_code}"
                }
            
            html = response.text
            
            iframe_pattern = r'<iframe[^>]*src="([^"]*pdfemb-data[^"]*)"'
            iframe_matches = re.findall(iframe_pattern, html, re.IGNORECASE)
            
            for iframe_src in iframe_matches:
                param_pattern = r'pdfemb-data=([^&"\']+)'
                param_match = re.search(param_pattern, iframe_src)
                
                if param_match:
                    base64_data = param_match.group(1)
                    pdf_url = PDFEmbedderExtractor._decode_pdfemb_data(base64_data)
                    
                    if pdf_url:
                        return {
                            'success': True,
                            'pdf_url': pdf_url,
                            'method': 'PDF Embedder (iframe)',
                            'details': f"Décodé depuis iframe avec pdfemb-data"
                        }
            
            direct_pattern = r'pdfemb-data[=:]["\']([^"\']+)["\']'
            direct_matches = re.findall(direct_pattern, html)
            
            for base64_data in direct_matches:
                pdf_url = PDFEmbedderExtractor._decode_pdfemb_data(base64_data)
                if pdf_url:
                    return {
                        'success': True,
                        'pdf_url': pdf_url,
                        'method': 'PDF Embedder (direct)',
                        'details': f"Décodé depuis attribut data"
                    }
            
            script_pattern = r'<script[^>]*>([^<]+)</script>'
            scripts = re.findall(script_pattern, html, re.IGNORECASE | re.DOTALL)
            
            for i, script in enumerate(scripts):
                if 'pdfemb' in script.lower() or 'pdf' in script.lower():
                    b64_pattern = r'["\'](eyJ[^"\']{50,})["\']'
                    b64_matches = re.findall(b64_pattern, script)
                    
                    for b64_data in b64_matches:
                        pdf_url = PDFEmbedderExtractor._decode_pdfemb_data(b64_data)
                        if pdf_url:
                            return {
                                'success': True,
                                'pdf_url': pdf_url,
                                'method': 'PDF Embedder (script)',
                                'details': f"Décodé depuis script JS n°{i+1}"
                            }
            
            viewer_patterns = [
                r'src="([^"]*viewer[^"]*\.pdf[^"]*)"',
                r'data-src="([^"]*\.pdf)"',
                r'pdf-url="([^"]*)"',
                r'["\'](https?://[^"\']+/viewer[^"\']*\.pdf)["\']'
            ]
            
            for pattern in viewer_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    if match and '.pdf' in match.lower():
                        pdf_url = match
                        if not pdf_url.startswith('http'):
                            if pdf_url.startswith('//'):
                                pdf_url = 'https:' + pdf_url
                            elif pdf_url.startswith('/'):
                                base_url = '/'.join(url.split('/')[:3])
                                pdf_url = base_url + pdf_url
                        
                        return {
                            'success': True,
                            'pdf_url': pdf_url,
                            'method': 'Viewer PDF',
                            'details': f"Trouvé via pattern: {pattern[:50]}..."
                        }
            
            return {
                'success': False,
                'pdf_url': None,
                'method': 'Non trouvé',
                'details': "Aucun pdfemb-data trouvé sur cette page."
            }
                
        except Exception as e:
            return {
                'success': False,
                'pdf_url': None,
                'method': 'Erreur',
                'details': f"Exception: {str(e)}"
            }
    
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
                        pdf_url_encoded = data['pdfemb-serverurl']
                        pdf_url = unquote(pdf_url_encoded)
                        return pdf_url
                    
                    for key, value in data.items():
                        if isinstance(value, str) and '.pdf' in value.lower():
                            pdf_url = unquote(value)
                            return pdf_url
                
                except json.JSONDecodeError:
                    pass
            
            url_patterns = [
                r'https?%3A%2F%2F[^"\']+\.pdf',
                r'https?://[^\s"\']+\.pdf',
                r'wp-content/uploads/[^"\']+\.pdf'
            ]
            
            for pattern in url_patterns:
                match = re.search(pattern, decoded_str, re.IGNORECASE)
                if match:
                    pdf_url = match.group(0)
                    if '%' in pdf_url:
                        pdf_url = unquote(pdf_url)
                    return pdf_url
            
            return None
            
        except Exception as e:
            return None
    
    @staticmethod
    def download_pdf(pdf_url: str) -> tuple:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,*/*',
                'Referer': 'https://www.elearning-cpge.com/'
            }
            
            response = requests.get(pdf_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                content = response.content
                
                if len(content) > 4 and content[:4] == b'%PDF':
                    return True, content, "PDF valide téléchargé"
                elif 'pdf' in response.headers.get('Content-Type', '').lower():
                    return True, content, "PDF détecté par Content-Type"
                else:
                    return False, None, "Le contenu n'est pas un PDF"
            else:
                return False, None, f"Erreur HTTP {response.status_code}"
                
        except Exception as e:
            return False, None, f"Erreur téléchargement: {str(e)}"


class ELearningPDFBot:
    def __init__(self, token: str):
        self.token = token
        self.extractor = PDFEmbedderExtractor()
        self.app = None
    
    async def start(self, update: Update, context):
        welcome = "Salaaam, m3ak Hiba, kan9d nkhrj lik PDF mn ay link dyal elearning-cpge.com. Sift liya 4i lien direct wlba9i 3liya <3."
        await update.message.reply_text(welcome)
    
    async def handle_message(self, update: Update, context):
        user_input = update.message.text.strip()
        
        if user_input.startswith('/'):
            return
        
        if 'elearning-cpge.com' not in user_input:
            await update.message.reply_text(
                "WA TA SIFT LIEN D ELEARNING M9AD!! Bhal hada matalan:\n"
                "https://www.elearning-cpge.com/maths-sup/equations-differentielles-lineaires/"
            )
            return
        
        url = user_input
        
        wait_msg = await update.message.reply_text("Sbeeeeeer...")
        
        try:
            await wait_msg.edit_text("Bchwiya 3linaaa...")
            result = self.extractor.extract_pdf_from_page(url)
            
            if result['success'] and result['pdf_url']:
                await wait_msg.edit_text("Hani b3da l9ito hehehe...")
                
                success, pdf_content, message = self.extractor.download_pdf(result['pdf_url'])
                
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
            logger.error(f"Erreur: {e}", exc_info=True)
            await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
    
    async def debug_mode(self, update: Update, context):
        if not context.args:
            await update.message.reply_text("mosamiha walakin kayn chi mochkil.")
            return
        
        url = context.args[0]
        
        wait_msg = await update.message.reply_text("Bchwiya 3linaaa...")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            html = response.text
            
            iframe_pattern = r'<iframe[^>]*src="([^"]*)"'
            iframes = re.findall(iframe_pattern, html, re.IGNORECASE)
            
            pdfemb_pattern = r'pdfemb-data[=:]["\']([^"\']+)["\']'
            pdfemb_matches = re.findall(pdfemb_pattern, html)
            
            base64_pattern = r'["\'](eyJ[^"\']{30,})["\']'
            base64_matches = re.findall(base64_pattern, html)
            
            report = (
                f"RAPPORT DEBUG\n\n"
                f"URL analysée: {url}\n"
                f"Statut HTTP: {response.status_code}\n"
                f"Taille HTML: {len(html):,} caractères\n\n"
                f"Iframes trouvés: {len(iframes)}\n"
            )
            
            for i, iframe in enumerate(iframes[:5]):
                report += f"  {i+1}. {iframe[:80]}...\n"
            
            report += f"\npdfemb-data trouvés: {len(pdfemb_matches)}\n"
            for i, data in enumerate(pdfemb_matches[:3]):
                report += f"  {i+1}. {data[:50]}...\n"
            
            report += f"\nChaînes base64: {len(base64_matches)}\n"
            for i, b64 in enumerate(base64_matches[:3]):
                report += f"  {i+1}. {b64[:50]}...\n"
            
            if pdfemb_matches:
                report += "\nTentative de décodage:\n"
                pdf_url = self.extractor._decode_pdfemb_data(pdfemb_matches[0])
                if pdf_url:
                    report += f"URL extraite: {pdf_url}\n"
                else:
                    report += "Échec du décodage\n"
            
            await wait_msg.edit_text(report)
            
        except Exception as e:
            await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
    
    async def start_bot(self):
        """Start the Telegram bot"""
        self.app = Application.builder().token(self.token).build()
        
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("debug", self.debug_mode))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("🤖 Bot PDF Embedder Extractor")
        logger.info("🎯 SPÉCIALISÉ pour elearning-cpge.com")
        logger.info("📡 Bot en cours de démarrage...")
        
        # Run polling in background
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("✅ Bot Telegram démarré avec succès!")
        
        # Keep the bot running
        await asyncio.Event().wait()
    
    async def stop_bot(self):
        """Stop the Telegram bot"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

async def health_check(request):
    """Health check endpoint for Railway"""
    return web.Response(text="Bot is running!", status=200)

async def start_web_server():
    """Start a simple web server for Railway health checks"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    port = int(os.getenv('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"✅ Health check server démarré sur le port {port}")
    return runner

async def main():
    """Main function to run both bot and web server"""
    # Get bot token from environment
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        logger.error("❌ ERREUR: BOT_TOKEN non défini")
        logger.info("ℹ️  Configurez la variable d'environnement BOT_TOKEN sur Railway")
        sys.exit(1)
    
    logger.info("🚀 Démarrage de l'application...")
    
    # Start the Telegram bot
    bot = ELearningPDFBot(BOT_TOKEN)
    
    # Start web server and bot concurrently
    web_runner = await start_web_server()
    
    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        logger.info("👋 Arrêt du bot...")
    finally:
        # Clean shutdown
        await bot.stop_bot()
        await web_runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Arrêt de l'application.")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
