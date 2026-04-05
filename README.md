# AnonyInfo - The Universal Open-Source OSINT Tool

AnonyInfo is a powerful, high-performance OSINT suite that gathers intelligence from across the web without requiring any private API keys or developer accounts. It features automatic input detection and asynchronous probing for maximum speed.

## Features

*   **Universal Input Detection:** Automatically handles Names, Usernames, Emails, Phone Numbers, Domains, IPs, and Image URLs.
*   **High-Speed Discovery:** Asynchronous probing of 80+ social media platforms.
*   **Network Intelligence:** Automatic DNS record resolution (MX, TXT, A, NS) and IP geolocation.
*   **Phone OSINT:** International formatting, country/carrier detection, and regional lookups.
*   **Reverse Image Search:** Instant generation of investigation links for Google Lens, Yandex, and Bing.
*   **Deep Web Search:** Clean, integrated web search results via DuckDuckGo.
*   **Investigation Links:** Automated generation of deep-search dorks for leaks, LinkedIn, and more.
*   **JSON Reporting:** Save all findings into structured report files.

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-username/AnonyInfo.git
    ```
2.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

```bash
# General Search (Name, Username, Email, Phone, Domain, IP, or Image URL)
python anonyinfo.py <target>

# Generate a JSON Report
python anonyinfo.py <target> --report
```

## Contributing

This tool is entirely free and open-source. Contributions are welcome!
