# VibeGenerator

A Streamlit application that generates Spotify playlists based on your Last.fm listening history. Create personalized playlists featuring your favorite artists and their top tracks.

## Features

- 🔍 Search your Last.fm listening history for specific artists
- 🎵 Create Spotify playlists with your scrobbled tracks
- ⭐ Optionally include top tracks from each artist
- 🎚️ Customize the number of top tracks to include (1-20)
- 🔄 Smart track matching that handles different naming formats
- 📊 Real-time progress tracking and status updates

## Prerequisites

- Python 3.7 or higher
- Last.fm account
- Spotify account
- Last.fm API credentials
- Spotify API credentials

## Installation

1. Clone this repository:
```bash
git clone https://github.com/RoelStierum/VibeGenerator.git
cd VibeGenerator
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your API credentials:
   - Get your Last.fm API credentials from [Last.fm API](https://www.last.fm/api/account/create)
   - Get your Spotify API credentials from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Update the configuration in `vibegen_streamlit.py`:
     ```python
     LASTFM_API_KEY = "YOUR_LASTFM_API_KEY"
     LASTFM_API_SECRET = "YOUR_LASTFM_API_SECRET"
     SPOTIPY_CLIENT_ID = "YOUR_SPOTIFY_CLIENT_ID"
     SPOTIPY_CLIENT_SECRET = "YOUR_SPOTIFY_CLIENT_SECRET"
     ```

## Usage

1. Run the Streamlit application:
```bash
python -m streamlit run vibegen_streamlit.py
```

2. In the web interface:
   - Enter your Last.fm username
   - Enter artist names (comma-separated)
   - Choose a name for your Spotify playlist
   - Optionally enable "Include top tracks" and select how many tracks per artist
   - Click "Generate Playlist"

3. The application will:
   - Search your Last.fm history for the specified artists
   - Find matching tracks on Spotify
   - Create a new playlist with all found tracks
   - Show you the playlist URL when complete

## Features in Detail

### Track Matching
- Smart matching algorithm that handles:
  - Different naming formats
  - Swapped track/artist information
  - Special characters and formatting differences
  - Case-insensitive matching

### Progress Tracking
- Real-time updates on:
  - Last.fm connection status
  - Track search progress
  - Playlist creation status
  - Found tracks count

### Error Handling
- Clear warnings for:
  - Artists not found
  - Tracks not found
  - API connection issues
  - Playlist creation problems

## Requirements

The application uses the following Python packages:
- streamlit
- pylast
- spotipy

See `requirements.txt` for specific versions.

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details.
