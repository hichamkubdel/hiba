#!/usr/bin/env python3
"""
Bot spécialisé pour elearning-cpge.com
Extrait automatiquement les PDFs des viewers PDF Embedder
"""

import asyncio
import requests
import re
import base64
import json
import logging
from urllib.parse import unquote, urljoin
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFEmbedderExtractor:
    """Extracteur spécialisé pour PDF Embedder d'elearning-cpge.com"""
    
    @staticmethod
    def extract_pdf_from_page(url: str) -> dict:
        """
        Analyse une page d'elearning-cpge.com et extrait le lien PDF
        Retourne: {'success': bool, 'pdf_url': str, 'method': str, 'details': str}
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            print(f"🔍 Analyse de: {url}")
            
            # 1. Récupérer la page
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'pdf_url': None,
                    'method': 'Erreur HTTP',
                    'details': f"HTTP {response.status_code}"
                }
            
            html = response.text
            
            # 2. Chercher le paramètre pdfemb-data (MÉTHODE PRINCIPALE)
            print("🔎 Recherche de pdfemb-data...")
            
            # Pattern pour trouver pdfemb-data dans les iframes
            iframe_pattern = r'<iframe[^>]*src="([^"]*pdfemb-data[^"]*)"'
            iframe_matches = re.findall(iframe_pattern, html, re.IGNORECASE)
            
            for iframe_src in iframe_matches:
                print(f"📦 Iframe trouvé: {iframe_src[:100]}...")
                
                # Extraire le paramètre pdfemb-data
                param_pattern = r'pdfemb-data=([^&"\']+)'
                param_match = re.search(param_pattern, iframe_src)
                
                if param_match:
                    base64_data = param_match.group(1)
                    print(f"🔐 pdfemb-data trouvé ({len(base64_data)} caractères)")
                    
                    # Décoder
                    pdf_url = PDFEmbedderExtractor._decode_pdfemb_data(base64_data)
                    
                    if pdf_url:
                        return {
                            'success': True,
                            'pdf_url': pdf_url,
                            'method': 'PDF Embedder (iframe)',
                            'details': f"Décodé depuis iframe avec pdfemb-data"
                        }
            
            # 3. Chercher pdfemb-data directement dans le HTML (sans iframe)
            print("🔎 Recherche directe de pdfemb-data...")
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
            
            # 4. Chercher dans les scripts JavaScript
            print("🔎 Recherche dans les scripts JS...")
            script_pattern = r'<script[^>]*>([^<]+)</script>'
            scripts = re.findall(script_pattern, html, re.IGNORECASE | re.DOTALL)
            
            for i, script in enumerate(scripts):
                if 'pdfemb' in script.lower() or 'pdf' in script.lower():
                    # Chercher base64 dans le script
                    b64_pattern = r'["\'](eyJ[^"\']{50,})["\']'  # JSON base64 commence par eyJ
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
            
            # 5. Méthode alternative: Chercher des URLs qui ressemblent à des viewers PDF
            print("🔎 Recherche de viewers PDF...")
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
            
            # 6. Si rien trouvé
            return {
                'success': False,
                'pdf_url': None,
                'method': 'Non trouvé',
                'details': (
                    "Aucun pdfemb-data trouvé sur cette page.\n"
                    "Le site utilise peut-être une autre méthode.\n"
                    "Vérifiez manuellement dans F12 → Network."
                )
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
        """Décoder les données pdfemb-data pour extraire l'URL PDF"""
        try:
            # Nettoyer la chaîne
            base64_str = base64_str.strip()
            
            # Ajouter le padding si nécessaire (base64 requiert longueur multiple de 4)
            padding = 4 - len(base64_str) % 4
            if padding != 4:
                base64_str += '=' * padding
            
            print(f"🔓 Décodage base64: {base64_str[:50]}...")
            
            # Décoder base64
            decoded_bytes = base64.b64decode(base64_str)
            decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
            
            print(f"📄 Données décodées: {decoded_str[:100]}...")
            
            # Essayer de parser comme JSON
            if '{' in decoded_str and '}' in decoded_str:
                try:
                    data = json.loads(decoded_str)
                    
                    # Chercher pdfemb-serverurl (le champ qui contient l'URL)
                    if 'pdfemb-serverurl' in data:
                        pdf_url_encoded = data['pdfemb-serverurl']
                        pdf_url = unquote(pdf_url_encoded)
                        print(f"✅ URL extraite: {pdf_url}")
                        return pdf_url
                    
                    # Chercher d'autres champs possibles
                    for key, value in data.items():
                        if isinstance(value, str) and '.pdf' in value.lower():
                            pdf_url = unquote(value)
                            print(f"✅ URL trouvée dans {key}: {pdf_url}")
                            return pdf_url
                
                except json.JSONDecodeError:
                    # Si ce n'est pas du JSON, chercher directement une URL
                    pass
            
            # Chercher une URL PDF directement dans le texte décodé
            url_patterns = [
                r'https?%3A%2F%2F[^"\']+\.pdf',  # URL encodée
                r'https?://[^\s"\']+\.pdf',       # URL directe
                r'wp-content/uploads/[^"\']+\.pdf' # Chemin WordPress
            ]
            
            for pattern in url_patterns:
                match = re.search(pattern, decoded_str, re.IGNORECASE)
                if match:
                    pdf_url = match.group(0)
                    # Décoder si URL encodée
                    if '%' in pdf_url:
                        pdf_url = unquote(pdf_url)
                    print(f"✅ URL extraite via regex: {pdf_url}")
                    return pdf_url
            
            return None
            
        except Exception as e:
            print(f"❌ Erreur décodage: {e}")
            return None
    
    @staticmethod
    def download_pdf(pdf_url: str) -> tuple:
        """Télécharge le PDF et retourne (succès, contenu, message)"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,*/*',
                'Referer': 'https://www.elearning-cpge.com/'
            }
            
            print(f"📥 Téléchargement: {pdf_url}")
            
            response = requests.get(pdf_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                content = response.content
                
                # Vérifier signature PDF
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
    """Bot spécialisé pour elearning-cpge.com"""
    
    def __init__(self, token: str):
        self.token = token
        self.extractor = PDFEmbedderExtractor()
    
    async def start(self, update: Update, context):
        """Commande /start"""
        welcome = """
Salaaam, m3ak Hiba, kan9d nkhrj lik PDF mn ay link dyal elearning-cpge.com. Sift liya 4i lien direct wlba9i 3liya <3.
        """
        await update.message.reply_text(welcome)
    
    async def handle_message(self, update: Update, context):
        """Gérer les messages (URLs)"""
        user_input = update.message.text.strip()
        
        # Ignorer les commandes
        if user_input.startswith('/'):
            return
        
        # Vérifier que c'est elearning-cpge.com
        if 'elearning-cpge.com' not in user_input:
            await update.message.reply_text(
                "WA TA SIFT LIEN D ELEARNING M9AD!! Bhal hada matalan:\n"
                "https://www.elearning-cpge.com/maths-sup/equations-differentielles-lineaires/"
            )
            return
        
        url = user_input
        
        # Message d'attente
        wait_msg = await update.message.reply_text("Sbeeeeeer...")
        
        try:
            # Étape 1: Extraire le PDF
            await wait_msg.edit_text("Bchwiya 3linaaa...")
            result = self.extractor.extract_pdf_from_page(url)
            
            # Étape 2: Afficher les résultats
            if result['success'] and result['pdf_url']:
                await wait_msg.edit_text("Hani b3da l9ito hehehe...")
                
                # Étape 3: Télécharger
                success, pdf_content, message = self.extractor.download_pdf(result['pdf_url'])
                
                if success and pdf_content:
                    # Générer nom de fichier
                    filename = result['pdf_url'].split('/')[-1] or "document.pdf"
                    filename = re.sub(r'[^\w\.-]', '_', filename)
                    if not filename.lower().endswith('.pdf'):
                        filename += '.pdf'
                    
                    # Envoyer le PDF
                    await update.message.reply_document(
                        document=pdf_content,
                        filename=filename,
                        caption="3la slamti hahwak pdf dyalk litlbti. U r welcome!"
                    )
                    
                    await wait_msg.delete()
                    
                else:
                    await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
            
            else:
                # Aucun pdfemb-data trouvé
                await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
                
        except Exception as e:
            logger.error(f"Erreur: {e}", exc_info=True)
            await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
    
    async def debug_mode(self, update: Update, context):
        """Commande /debug - Mode debug avancé"""
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
            
            # Chercher tous les iframes
            iframe_pattern = r'<iframe[^>]*src="([^"]*)"'
            iframes = re.findall(iframe_pattern, html, re.IGNORECASE)
            
            # Chercher pdfemb-data
            pdfemb_pattern = r'pdfemb-data[=:]["\']([^"\']+)["\']'
            pdfemb_matches = re.findall(pdfemb_pattern, html)
            
            # Chercher base64
            base64_pattern = r'["\'](eyJ[^"\']{30,})["\']'
            base64_matches = re.findall(base64_pattern, html)
            
            # Construire rapport debug
            report = (
                f"🔧 **RAPPORT DEBUG**\n\n"
                f"**URL analysée:** `{url}`\n"
                f"**Statut HTTP:** {response.status_code}\n"
                f"**Taille HTML:** {len(html):,} caractères\n\n"
                f"**📦 Iframes trouvés:** {len(iframes)}\n"
            )
            
            for i, iframe in enumerate(iframes[:5]):  # 5 premiers
                report += f"  {i+1}. `{iframe[:80]}...`\n"
            
            report += f"\n**🔐 pdfemb-data trouvés:** {len(pdfemb_matches)}\n"
            for i, data in enumerate(pdfemb_matches[:3]):
                report += f"  {i+1}. `{data[:50]}...`\n"
            
            report += f"\n**🔐 Chaînes base64:** {len(base64_matches)}\n"
            for i, b64 in enumerate(base64_matches[:3]):
                report += f"  {i+1}. `{b64[:50]}...`\n"
            
            # Essayer de décoder le premier pdfemb-data
            if pdfemb_matches:
                report += "\n**🔓 Tentative de décodage:**\n"
                pdf_url = self.extractor._decode_pdfemb_data(pdfemb_matches[0])
                if pdf_url:
                    report += f"✅ **URL extraite:** `{pdf_url}`\n"
                else:
                    report += "❌ **Échec du décodage**\n"
            
            await wait_msg.edit_text(report, parse_mode='Markdown')
            
        except Exception as e:
            await wait_msg.edit_text("mosamiha walakin kayn chi mochkil.")
    
    def run(self):
        """Lancer le bot"""
        app = Application.builder().token(self.token).build()
        
        # Commandes
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("debug", self.debug_mode))
        
        # Messages (URLs)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        print("=" * 70)
        print("🤖 BOT PDF EMBEDDER EXTRACTOR")
        print("🎯 SPÉCIALISÉ pour elearning-cpge.com")
        print("🔍 Recherche automatique de pdfemb-data")
        print("=" * 70)
        print("\n📝 En attente de liens elearning-cpge.com...")
        
        app.run_polling()


# TEST RAPIDE DU DÉCODAGE
def test_decodage():
    """Tester le décodage avec un exemple connu"""
    print("🧪 Test de décodage...")
    
    # Exemple de données pdfemb-data (extraites d'une vraie page)
    example_base64 = "eyJpbmRleCI6MSwicGRmSUQiOjkyNDUsInBkZmVtYi1zZXJ2ZXVybCI6Imh0dHBzJTNBJTJGJTJGd3d3LmVsZWFybmluZy1jcGdlLmNvbSUyRndwLWNvbnRlbnQlMkZ1cGxvYWRzJTJGc2VjdXJlcGRmcyUyRjIwMjAlMkYwOSUyRmVsZWMxLnBkZiJ9"
    
    extractor = PDFEmbedderExtractor()
    result = extractor._decode_pdfemb_data(example_base64)
    
    if result:
        print(f"✅ Test réussi! URL décodée: {result}")
        return True
    else:
        print("❌ Test échoué")
        return False


# POINT D'ENTRÉE
if __name__ == "__main__":
    # Essaie de récupérer le token depuis les variables d'environnement (Railway)
    # Sinon, utilise le token en dur
    import os
    BOT_TOKEN = os.getenv('BOT_TOKEN', '8400311133:AAGK_ZvbB8ClU0L68P0TcLxFTP0KKYyzIC0')
    
    print("🚀 Lancement du Bot PDF Embedder Extractor...")
    
    print("🤖 Bot prêt à recevoir des liens elearning-cpge.com")
    print("=" * 70)
    
    try:
        bot = ELearningPDFBot(BOT_TOKEN)
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Arrêt du bot.")
    except Exception as e:

        print(f"❌ Erreur: {e}")
