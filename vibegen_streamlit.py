import streamlit as st
import pylast
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
from datetime import datetime
import os
import concurrent.futures
from typing import List, Tuple

# --- CONFIG ---

LASTFM_API_KEY = "YOUR_KEY"
LASTFM_API_SECRET = "YOUR_SECRET"

SPOTIPY_CLIENT_ID = "YOUR_KEY"
SPOTIPY_CLIENT_SECRET = "YOUR_SECRET"

SPOTIPY_REDIRECT_URI = "http://127.0.0.1:8888/callback"

# Initialize session state
if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'status' not in st.session_state:
    st.session_state.status = ""
if 'found_tracks' not in st.session_state:
    st.session_state.found_tracks = []
if 'top_tracks' not in st.session_state:
    st.session_state.top_tracks = []

def update_progress(current, total, prefix='', suffix=''):
    st.session_state.progress = int(100 * current / total)
    st.session_state.status = f"{prefix} {suffix}"

def add_tracks_to_playlist_in_batches(sp, user_id, playlist_id, track_ids, batch_size=100):
    """Voeg tracks toe aan een playlist in batches van maximaal 100 tracks per keer"""
    total_tracks = len(track_ids)
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_tracks, batch_size):
        batch = track_ids[i:i + batch_size]
        try:
            sp.user_playlist_add_tracks(user=user_id, playlist_id=playlist_id, tracks=batch)
            progress = min(100, int((i + len(batch)) / total_tracks * 100))
            progress_bar.progress(progress)
            status_text.text(f"Tracks toevoegen: {i + len(batch)}/{total_tracks}")
        except Exception as e:
            st.error(f"Fout bij toevoegen van batch {i//batch_size + 1}: {str(e)}")
            continue

def get_artist_top_tracks(sp, artist_name, limit=10):
    try:
        # Zoek de artiest op Spotify met exacte match
        results = sp.search(q=f'artist:"{artist_name}"', type='artist', limit=1)
        if not results['artists']['items']:
            st.warning(f"⚠️ Artiest '{artist_name}' niet gevonden op Spotify")
            return []
            
        artist = results['artists']['items'][0]
        # Controleer of de naam exact overeenkomt (case-insensitive)
        if artist['name'].lower() != artist_name.lower():
            st.warning(f"⚠️ Artiest '{artist_name}' niet exact gevonden op Spotify (gevonden: {artist['name']})")
            return []
            
        artist_id = artist['id']
        
        # Haal de top tracks op
        top_tracks = sp.artist_top_tracks(artist_id)
        return [(track['id'], track['name'], track['artists'][0]['name']) for track in top_tracks['tracks'][:limit]]
    except Exception as e:
        st.warning(f"⚠️ Kon top tracks niet ophalen voor {artist_name}: {str(e)}")
        return []

def process_track_batch(args):
    """Verwerk een batch tracks in een aparte thread"""
    user, time_to, batch_size, artist_names = args
    try:
        recent_tracks = user.get_recent_tracks(limit=batch_size, time_to=time_to)
        if not recent_tracks:
            return []
            
        found_tracks = []
        for item in recent_tracks:
            try:
                track = item.track
                if track and track.artist:
                    for artist_name in artist_names:
                        def normalize_name(name):
                            # Convert to lowercase and strip
                            name = name.lower().strip()
                            # Remove special characters but keep spaces and &
                            name = ''.join(c for c in name if c.isalnum() or c.isspace() or c == '&')
                            return ' '.join(name.split())  # Normalize spaces
                        
                        def is_match(artist1, artist2):
                            # Normalize both names
                            norm1 = normalize_name(artist1)
                            norm2 = normalize_name(artist2)
                            
                            # Exact match after normalization
                            if norm1 == norm2:
                                return True
                                
                            # Split into words and check if all words from one are in the other
                            words1 = set(norm1.split())
                            words2 = set(norm2.split())
                            
                            # If one name is a subset of the other (e.g., "Dimitri Vegas" in "Dimitri Vegas & Like Mike")
                            if words1.issubset(words2) or words2.issubset(words1):
                                # Additional check to prevent false matches with single words
                                if len(words1) > 1 or len(words2) > 1:  # At least one name has multiple words
                                    return True
                            
                            return False
                        
                        if is_match(track.artist.name, artist_name):
                            found_tracks.append((track.title, track.artist.name))
                            print(f"✅ Match gevonden: {track.artist.name} (gezocht: {artist_name})")
                            break
            except Exception as e:
                print(f"⚠️ Fout bij verwerken van track: {str(e)}")
                continue
        return found_tracks
    except Exception as e:
        print(f"⚠️ Fout bij verwerken van batch: {str(e)}")
        return []

def get_lastfm_tracks(username, artist_names, limit=None):
    try:
        st.info("🔌 Verbinden met Last.fm...")
        
        try:
            network = pylast.LastFMNetwork(api_key=LASTFM_API_KEY, api_secret=LASTFM_API_SECRET)
            st.success("✅ Last.fm netwerk verbinding gemaakt")
        except Exception as e:
            st.error(f"❌ Fout bij maken van netwerk verbinding: {str(e)}")
            return []
        
        try:
            st.info(f"👤 Ophalen gebruiker {username}...")
            user = network.get_user(username)
            st.success(f"✅ Gebruiker {username} gevonden")
        except Exception as e:
            st.error(f"❌ Fout bij ophalen gebruiker: {str(e)}")
            return []
        
        st.info("📡 Zoek alle scrobbles...")
        seen = set()
        filtered = []
        total_processed = 0
        
        try:
            # Haal eerst het totale aantal scrobbles op
            total_scrobbles = user.get_playcount()
            st.info(f"Totaal aantal scrobbles: {total_scrobbles}")
            
            # Bereken batch size en aantal batches
            batch_size = 950  # Grotere batches voor efficiëntie
            current_time = int(time.time())
            progress_bar = st.progress(0)
            status_text = st.empty()
            found_tracks_text = st.empty()
            
            # Maak een set van genormaliseerde artiestnamen voor snellere matching
            normalized_artists = set()
            for artist in artist_names:
                def normalize_name(name):
                    name = name.lower().strip()
                    name = ''.join(c for c in name if c.isalnum() or c.isspace() or c == '&')
                    return ' '.join(name.split())
                normalized_artists.add(normalize_name(artist))
            
            empty_batch_count = 0
            total_batches_processed = 0
            
            while empty_batch_count < 3:  # Stop na 3 lege batches
                total_batches_processed += 1
                status_text.text(f"Batch {total_batches_processed} - {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d')}")
                
                try:
                    # Haal tracks op voor deze batch
                    recent_tracks = user.get_recent_tracks(limit=batch_size, time_to=current_time)
                    
                    if not recent_tracks:
                        empty_batch_count += 1
                        current_time = current_time - (30 * 24 * 60 * 60)  # Ga een maand terug
                        continue
                    
                    # Reset lege batch teller als we tracks vinden
                    empty_batch_count = 0
                    
                    # Verwerk de tracks
                    for item in recent_tracks:
                        try:
                            track = item.track
                            if track and track.artist:
                                # Normalize de artiestnaam
                                artist_name = normalize_name(track.artist.name)
                                
                                # Check of de genormaliseerde naam in onze set zit
                                if artist_name in normalized_artists:
                                    key = (track.title.lower(), track.artist.name.lower())
                                    if key not in seen:
                                        seen.add(key)
                                        filtered.append((track.title, track.artist.name))
                                        found_tracks_text.text(f"✅ Track gevonden: {track.title} - {track.artist.name}")
                        except Exception as e:
                            continue
                    
                    # Update timestamp voor volgende batch
                    if recent_tracks:
                        last_track = recent_tracks[-1]
                        current_time = int(last_track.timestamp)
                    else:
                        current_time = current_time - (30 * 24 * 60 * 60)  # Ga een maand terug
                        
                except Exception as e:
                    current_time = current_time - (30 * 24 * 60 * 60)  # Ga een maand terug
                    continue
                
                if current_time < 0:  # Stop als we bij het begin van de tijd zijn
                    break
                
                # Update progress bar
                progress = min(100, int((total_batches_processed * batch_size / total_scrobbles) * 100))
                progress_bar.progress(progress)
            
            st.success(f"✅ {len(filtered)} unieke tracks gevonden van alle opgegeven artiesten.")
            return filtered
            
        except Exception as e:
            st.error(f"❌ Fout bij ophalen tracks: {str(e)}")
            return []
            
    except Exception as e:
        st.error(f"❌ Onverwachte fout: {str(e)}")
        return []

def find_spotify_tracks(sp, track_list):
    found_tracks = []
    total_tracks = len(track_list)
    st.info(f"🔍 Zoek {total_tracks} tracks op Spotify...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    found_tracks_text = st.empty()
    
    for i, (title, artist) in enumerate(track_list, 1):
        try:
            status_text.text(f"Zoek track {i}/{total_tracks}: {title[:30]}...")
            progress_bar.progress(i / total_tracks)
            
            # Probeer verschillende zoekstrategieën
            queries = [
                f'track:"{title}" artist:"{artist}"',  # Originele exacte match
                f'track:"{artist}" artist:"{title}"',  # Mogelijk omgedraaid
                f'track:"{title}"',  # Alleen track naam
                f'artist:"{artist}" track:"{title}"',  # Andere volgorde
            ]
            
            found = False
            for query in queries:
                result = sp.search(q=query, type="track", limit=5)  # Verhoog limit voor meer resultaten
                items = result["tracks"]["items"]
                
                if items:
                    # Controleer alle gevonden tracks
                    for track in items:
                        # Vergelijk namen (case-insensitive en zonder speciale tekens)
                        track_name = ''.join(c for c in track['name'].lower() if c.isalnum() or c.isspace())
                        artist_name = ''.join(c for c in track['artists'][0]['name'].lower() if c.isalnum() or c.isspace())
                        search_title = ''.join(c for c in title.lower() if c.isalnum() or c.isspace())
                        search_artist = ''.join(c for c in artist.lower() if c.isalnum() or c.isspace())
                        
                        # Check of de namen overeenkomen (in beide richtingen)
                        if ((track_name == search_title and artist_name == search_artist) or
                            (track_name == search_artist and artist_name == search_title)):
                            found_tracks.append((track["id"], track["name"], track["artists"][0]["name"]))
                            found_tracks_text.text(f"✅ Track gevonden op Spotify: {track['name']} - {track['artists'][0]['name']}")
                            found = True
                            break
                
                if found:
                    break
            
            if not found:
                st.warning(f"⚠️ Track '{title}' van '{artist}' niet gevonden op Spotify")
                
        except Exception as e:
            st.warning(f"⚠️ Fout bij zoeken naar track '{title}': {str(e)}")
            continue
    
    st.success(f"✅ {len(found_tracks)} tracks gevonden op Spotify")
    return found_tracks

def create_playlist(sp, user_id, name, track_ids):
    playlist = sp.user_playlist_create(user=user_id, name=name, public=False)
    if not track_ids:
        st.warning("⚠️ Geen tracks gevonden op Spotify. Lege playlist wordt niet gevuld.")
        return playlist["external_urls"]["spotify"]

    # Voeg tracks toe in batches
    add_tracks_to_playlist_in_batches(sp, user_id, playlist["id"], track_ids)
    return playlist["external_urls"]["spotify"]

def main():
    st.set_page_config(page_title="VibeGenerator", page_icon="🎵", layout="wide")
    
    # Container voor status updates
    status_container = st.container()
    
    st.title("🎵 VibeGenerator")
    st.markdown("""
    Maak een Spotify playlist van je geluisterde Last.fm tracks!
    """)
    
    with st.form("input_form"):
        username = st.text_input("Last.fm gebruikersnaam")
        artist_input = st.text_input("Artiesten (komma-gescheiden)")
        playlist_name = st.text_input("Spotify playlist naam")
        include_top_tracks = st.checkbox("Voeg top tracks van artiesten toe", value=True)
        
        if include_top_tracks:
            top_tracks_count = st.slider(
                "Aantal top tracks per artiest",
                min_value=1,
                max_value=20,
                value=10,
                help="Kies hoeveel van de populairste tracks van elke artiest je wilt toevoegen"
            )
        
        submitted = st.form_submit_button("Genereer Playlist")
    
    if submitted:
        if not all([username, artist_input, playlist_name]):
            st.error("Vul alle velden in!")
            return
            
        artists = [a.strip() for a in artist_input.split(",")]
        
        # Verbind met Spotify
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=SPOTIPY_CLIENT_ID,
                client_secret=SPOTIPY_CLIENT_SECRET,
                redirect_uri=SPOTIPY_REDIRECT_URI,
                scope="playlist-modify-private playlist-modify-public"
            ))
            user_id = sp.me()["id"]
        except Exception as e:
            st.error(f"Fout bij verbinden met Spotify: {str(e)}")
            return
            
        # Haal Last.fm tracks op
        all_lastfm_tracks = get_lastfm_tracks(username, artists)
        
        if not all_lastfm_tracks:
            st.error("Geen tracks gevonden voor de opgegeven artiesten.")
            return
            
        # Zoek tracks op Spotify
        st.session_state.found_tracks = find_spotify_tracks(sp, all_lastfm_tracks)
        
        # Voeg top tracks toe als aangevinkt
        if include_top_tracks:
            st.info(f"🎵 Top {top_tracks_count} tracks van artiesten toevoegen...")
            st.session_state.top_tracks = []
            for artist in artists:
                artist_top_tracks = get_artist_top_tracks(sp, artist, limit=top_tracks_count)
                st.session_state.top_tracks.extend(artist_top_tracks)
            
            # Verwijder dubbele tracks
            all_tracks = st.session_state.found_tracks + st.session_state.top_tracks
            unique_tracks = []
            seen_ids = set()
            for track in all_tracks:
                if track[0] not in seen_ids:
                    seen_ids.add(track[0])
                    unique_tracks.append(track)
            
            st.success(f"✅ Totaal {len(unique_tracks)} tracks (inclusief top tracks)")
        else:
            unique_tracks = st.session_state.found_tracks
        
        if not unique_tracks:
            st.error("Geen tracks gevonden op Spotify.")
            return
            
        # Maak playlist aan
        try:
            playlist_url = create_playlist(sp, user_id, playlist_name, [track[0] for track in unique_tracks])
            st.success(f"✅ Playlist aangemaakt!")
            st.markdown(f"[Open playlist in Spotify]({playlist_url})")
            
            # Toon track overzicht
            with st.expander("Bekijk alle tracks in de playlist"):
                st.subheader("Last.fm Tracks")
                for track_id, title, artist in st.session_state.found_tracks:
                    st.write(f"🎵 {title} - {artist}")
                
                if include_top_tracks and st.session_state.top_tracks:
                    st.subheader(f"Top {top_tracks_count} Tracks per Artiest")
                    for track_id, title, artist in st.session_state.top_tracks:
                        st.write(f"⭐ {title} - {artist}")
                
                st.write(f"\nTotaal aantal tracks: {len(unique_tracks)}")
                
        except Exception as e:
            st.error(f"Fout bij aanmaken playlist: {str(e)}")

if __name__ == "__main__":
    main() 