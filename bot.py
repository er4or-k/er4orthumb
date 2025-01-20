from pyrogram import Client, filters
import pymongo
import os
from dotenv import load_dotenv
import subprocess
from PIL import Image
import asyncio

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
DB_URI = os.getenv("DB_URI")
DB_NAME = os.getenv("DB_NAME")

# Initialize MongoDB
mongo_client = pymongo.MongoClient(DB_URI)
db = mongo_client[DB_NAME]
users_collection = db["users"]

# Initialize Pyrogram bot
bot = Client("thumbnail_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Function to resize thumbnail (if necessary)
def resize_thumbnail(thumbnail_path):
    resized_path = f"{thumbnail_path}_resized.jpg"
    with Image.open(thumbnail_path) as img:
        img.thumbnail((320, 320))  # Resize to maximum allowed dimensions
        img.save(resized_path, "JPEG", quality=85)
    return resized_path

# Command to Start
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply("Hello! I'm your thumbnail bot. Use /setthumb to set a thumbnail and send me documents to update them!")

# Command to Set Thumbnail
@bot.on_message(filters.command("setthumb") & filters.private)
async def set_thumbnail(client, message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("❌ Reply to a photo to set it as the thumbnail!")
        return

    await message.reply("⏳ Downloading the thumbnail...")
    thumbnail_path = await client.download_media(message.reply_to_message.photo.file_id)
    users_collection.update_one(
        {"user_id": message.from_user.id},
        {"$set": {"thumbnail_path": thumbnail_path}},
        upsert=True
    )
    await message.reply("✅ Thumbnail set successfully!")

# Handle Batch Files Sent to the Bot
@bot.on_message(filters.media_group & filters.private)
async def handle_batch_files(client, message):
    user_data = users_collection.find_one({"user_id": message.from_user.id})
    if not user_data or "thumbnail_path" not in user_data:
        await message.reply("❌ No thumbnail set! Use /setthumb to set a thumbnail first.")
        return

    thumbnail_path = user_data["thumbnail_path"]
    file_id = message.document.file_id
    file_name = message.document.file_name

    # Resize thumbnail if necessary
    resized_thumbnail = resize_thumbnail(thumbnail_path)

    # Process each file in the batch concurrently
    tasks = []
    for media in message.media_group:
        tasks.append(process_file(client, message, media, resized_thumbnail))

    await asyncio.gather(*tasks)  # Process all files concurrently
    await message.reply("✅ All files processed successfully!")

async def process_file(client, message, media, thumbnail_path):
    file_id = media.document.file_id
    file_name = media.document.file_name

    await message.reply("⏳ Downloading your file...")
    file_path = await client.download_media(file_id)
    await message.reply("✅ File downloaded successfully!")

    await message.reply("⏳ Uploading your file with the custom thumbnail...")
    await client.send_document(
        chat_id=message.chat.id,
        document=file_path,
        thumb=thumbnail_path,
        file_name=file_name,  # Ensure the original name is retained
        caption=f"✅ File updated with thumbnail:\n**{file_name}**"
    )
    os.remove(file_path)

# Handle Single File Sent to the Bot
@bot.on_message(filters.document & filters.private)
async def handle_file(client, message):
    user_data = users_collection.find_one({"user_id": message.from_user.id})
    if not user_data or "thumbnail_path" not in user_data:
        await message.reply("❌ No thumbnail set! Use /setthumb to set a thumbnail first.")
        return

    thumbnail_path = user_data["thumbnail_path"]
    file_id = message.document.file_id
    file_name = message.document.file_name

    # Resize thumbnail if necessary
    resized_thumbnail = resize_thumbnail(thumbnail_path)

    await message.reply("⏳ Downloading your file...")
    file_path = await client.download_media(file_id)
    await message.reply("✅ File downloaded successfully!")

    await message.reply("⏳ Uploading your file with the custom thumbnail...")
    await client.send_document(
        chat_id=message.chat.id,
        document=file_path,
        thumb=resized_thumbnail,
        file_name=file_name,  # Ensure the original name is retained
        caption=f"✅ File updated with thumbnail:\n**{file_name}**"
    )
    os.remove(file_path)

# File Cleanup
@bot.on_message(filters.command("cleanup") & filters.private)
async def cleanup_thumbnails(client, message):
    user_data = users_collection.find_one({"user_id": message.from_user.id})
    if user_data and "thumbnail_path" in user_data:
        thumbnail_path = user_data["thumbnail_path"]
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        users_collection.update_one({"user_id": message.from_user.id}, {"$unset": {"thumbnail_path": ""}})
        await message.reply("✅ Thumbnail cleaned up successfully!")
    else:
        await message.reply("❌ No thumbnail found to clean up!")

# Start Pyrogram bot in a background task
def start_bot():
    bot.run()

if __name__ == "__main__":
    # Start both Flask and Pyrogram bot using subprocess
    subprocess.Popen(["python3", "app.py"])  # Start Flask app on a separate process
    start_bot()  # Run Pyrogram bot
