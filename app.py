#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os
import subprocess
import aria2p
import time

# Constants
BASE_URL = 'http://www.loyalbooks.com/Top_100'
AUDIOBOOKS_DIR = 'audiobooks'
PAGE = 1  # Start from page 1
ARIA2C_SECRET = "your_secret_token"


def start_aria2c():
    """Starts the aria2c process with RPC enabled."""
    aria2c_cmd = [
        "aria2c", "--enable-rpc", "--rpc-listen-all",
        f"--rpc-secret={ARIA2C_SECRET}", "--disable-ipv6"
    ]
    subprocess.Popen(aria2c_cmd)
    # Give aria2c some time to start
    time.sleep(2)


def fetch_books(page):
    """Fetches the list of books from a specific page of the LoyalBooks Top 100 page."""
    try:
        response = requests.get(f'{BASE_URL}/{page}')
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        book_entries = soup.find_all('td', class_='layout2-blue')

        books = []
        for entry in book_entries:
            link_tag = entry.find('a', href=True)
            link = f'http://www.loyalbooks.com{link_tag["href"]}' if link_tag else None

            title_tag = entry.find('b')
            if not title_tag:
                continue

            title = title_tag.text.strip()
            author = 'Unknown Author'
            next_node = title_tag.find_next_sibling()
            while next_node:
                if next_node.name is None and next_node.strip():
                    author = next_node.strip()
                    break
                next_node = next_node.find_next_sibling()

            cover_image = f'http://www.loyalbooks.com{entry.find("img")["src"]}' if entry.find(
                'img') else None

            books.append({
                'title': title,
                'author': author,
                'link': link,
                'cover_image': cover_image
            })
        return books
    except requests.RequestException as e:
        print(f"Error fetching books: {e}")
        return []


def get_pagination_info(soup):
    """Extract pagination information from the page."""
    pagination_info = {'current_page': PAGE, 'total_pages': PAGE}
    result_pages_div = soup.find('div', class_='result-pages')
    if result_pages_div:
        pagination_text = result_pages_div.get_text(strip=True)
        if 'Page' in pagination_text and 'of' in pagination_text:
            try:
                parts = pagination_text.split('Page ')[1].split(' of ')
                pagination_info['current_page'] = int(parts[0])
                pagination_info['total_pages'] = int(parts[1].replace('>', ''))
            except (ValueError, IndexError):
                print(
                    f"Warning: Pagination text parsing failed with value '{pagination_text}'")

        pagination_info['has_previous'] = pagination_info['current_page'] - \
            1 if pagination_info['current_page'] > 1 else None
        pagination_info['has_next'] = pagination_info['current_page'] + \
            1 if pagination_info['current_page'] < pagination_info['total_pages'] else None

    return pagination_info


def display_books(books):
    """Displays the list of books and their options to the user."""
    print("Available books:")
    for idx, book in enumerate(books, start=1):
        print(f"{idx}. {book['title']} by {book['author']}")
    print()


def fetch_rss_feed(url):
    """Fetch and parse the RSS feed."""
    try:
        response = requests.get(f'{url}/feed')
        response.raise_for_status()
        return ET.fromstring(response.content)
    except requests.RequestException as e:
        print(f"Error fetching RSS feed: {e}")
        return None


def download_book(rss_feed):
    """Download audiobooks based on the RSS feed using aria2p."""
    title_element = rss_feed.find('.//title')
    book_title = title_element.text.strip(
    ) if title_element is not None else 'unknown_title'
    book_title_cleaned = book_title.split(
        ' by ')[0].strip().lower().replace(' ', '-').replace("'", '')

    book_dir = os.path.join(AUDIOBOOKS_DIR, book_title_cleaned)
    os.makedirs(book_dir, exist_ok=True)

    mp3_urls = [item.find('enclosure').get('url') for item in rss_feed.findall(
        './/item') if item.find('enclosure') is not None]

    # Initialize aria2p client
    aria2 = aria2p.Client(
        host="http://localhost",
        port=6800,
        secret=ARIA2C_SECRET
    )

    # Create a download manager
    download_manager = aria2p.API(aria2)

    # Add each URL to the download manager
    for url in mp3_urls:
        try:
            download_manager.add_uris([url], options={"dir": book_dir})
        except Exception as e:
            print(f"Error adding URL to aria2p: {e}")

    print("Download started!")


def main():
    """Main function to handle user input and download."""
    global PAGE

    start_aria2c()

    while True:
        response = requests.get(f'{BASE_URL}/{PAGE}')
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        books = fetch_books(PAGE)
        if not books:
            print("No books found or there was an error fetching the book list.")
            return

        display_books(books)

        pagination_info = get_pagination_info(soup)
        current_page = pagination_info.get('current_page', PAGE)
        total_pages = pagination_info.get('total_pages', 'unknown')
        print(f"Page {current_page} of {total_pages}")

        while True:
            choice = input(
                "Enter the number of the book you want to download, or 'n' for next page, 'p' for previous page: ").strip().lower()
            if choice.isdigit():
                choice = int(choice)
                if 1 <= choice <= len(books):
                    selected_book = books[choice - 1]
                    if selected_book['link']:
                        rss_feed = fetch_rss_feed(selected_book['link'])
                        if rss_feed:
                            download_book(rss_feed)
                        else:
                            print("Failed to fetch the RSS feed. Please try again.")
                    break
                else:
                    print(
                        f"Invalid choice. Please enter a number between 1 and {len(books)}.")
            elif choice == 'n':
                if pagination_info.get('has_next'):
                    PAGE += 1
                    break
                else:
                    print("No next page available.")
            elif choice == 'p':
                if pagination_info.get('has_previous'):
                    PAGE -= 1
                    break
                else:
                    print("No previous page available.")
            else:
                print(
                    "Invalid input. Please enter a number, 'n' for next page, or 'p' for previous page.")


if __name__ == "__main__":
    # Ensure the audiobooks directory exists
    os.makedirs(AUDIOBOOKS_DIR, exist_ok=True)
    main()
