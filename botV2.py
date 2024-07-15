import logging
import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext
import feedparser
import time
import asyncio
import os
import json

# Configurez les logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Remplacez par le token de votre bot
TELEGRAM_BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
# Remplacez par l'identifiant de votre canal
TELEGRAM_CHANNEL_ID = '-'
# Liste des URLs des flux RSS
RSS_FEEDS = [
    'https://www.francetvinfo.fr/titres.rss',
    'https://www.lemonde.fr/rss',
    'https://www.france24.com/fr/rss',
    'https://cyberveille.curated.co/issues.rss',
    'https://www.bing.com/news/search?q=cybers%C3%A9curit%C3%A9&qft=sortbydate%3d%221%22%2Binterval%3d%227%22&form=YFNR&format=rss&cc=fr'
]

# Fichier pour enregistrer les articles envoyés
SENT_ARTICLES_FILE = 'sent_articles.json'

# Charger les articles envoyés depuis le fichier
def load_sent_articles():
    if os.path.exists(SENT_ARTICLES_FILE):
        with open(SENT_ARTICLES_FILE, 'r') as f:
            return set(json.load(f))
    return set()

# Enregistrer les articles envoyés dans le fichier
def save_sent_articles(sent_articles):
    with open(SENT_ARTICLES_FILE, 'w') as f:
        json.dump(list(sent_articles), f)

# Charger les articles envoyés
sent_articles = load_sent_articles()

# Fonction pour vérifier les flux RSS et envoyer les nouvelles au canal
async def check_feeds(context: CallbackContext):
    global sent_articles
    logger.info('Vérification des flux RSS...')
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        logger.info(f'Flux {feed_url} lu, {len(feed.entries)} articles trouvés.')
        for entry in feed.entries:
            article_id = entry.get('id', entry.link)  # Utiliser 'id' si présent, sinon 'link'
            if article_id in sent_articles:
                logger.info(f'Article {entry.title} déjà envoyé, ignoré.')
                continue
            logger.info(f'Article trouvé: {entry.title}')
            if hasattr(entry, 'published_parsed'):
                published_time = time.mktime(entry.published_parsed)
                logger.info(f'Article publié à: {time.strftime("%Y-%m-%d %H:%M:%S", entry.published_parsed)}')
                # Filtrer les articles publiés dans les dernières 4 heures
                if time.time() - published_time < 14400:  # 4 heures = 14400 secondes
                    message = f"{entry.title}\n{entry.link}"
                    try:
                        await context.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
                        logger.info(f'Article envoyé: {entry.title}')
                        sent_articles.add(article_id)
                        save_sent_articles(sent_articles)
                        await asyncio.sleep(2)  # Ajouter un délai de 2 secondes entre les envois de messages
                    except telegram.error.RetryAfter as e:
                        logger.warning(f'Flood control exceeded. Retry in {e.retry_after} seconds.')
                        await asyncio.sleep(e.retry_after)
                        await context.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
                        logger.info(f'Article envoyé après réessai: {entry.title}')
                        sent_articles.add(article_id)
                        save_sent_articles(sent_articles)
                    except telegram.error.TimedOut:
                        logger.warning(f'Envoi du message pour {entry.title} a expiré. Réessai...')
                        await asyncio.sleep(5)  # Attendre 5 secondes avant de réessayer
                        await context.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
                        logger.info(f'Article envoyé après réessai: {entry.title}')
                        sent_articles.add(article_id)
                        save_sent_articles(sent_articles)
                else:
                    logger.info(f'Article {entry.title} ignoré car publié il y a plus de 4 heures.')
            else:
                logger.warning(f'Article {entry.title} n\'a pas de date de publication.')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Bot started!')
    logger.info('Commande /start reçue.')

async def send_startup_message(application: Application):
    # Envoyer un message au canal pour indiquer que le bot a démarré
    await application.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text="Le bot a démarré et est prêt à vérifier les flux RSS.")
    logger.info('Message de démarrage envoyé.')

async def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    # Création du JobQueue
    job_queue = application.job_queue
    logger.info('Ajout de la tâche de vérification des flux RSS au JobQueue.')
    job_queue.run_repeating(check_feeds, interval=300, first=10)  # Vérifier toutes les 15 minutes

    await application.initialize()  # Initialiser l'application
    await application.start()
    await application.updater.start_polling()

    # Envoyer un message de démarrage
    await send_startup_message(application)

    # Bloquer la boucle d'événements pour maintenir l'application en cours d'exécution
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
