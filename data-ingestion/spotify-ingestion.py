import requests
import pandas as pd
import pandas_gbq
from urllib.parse import quote
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path='./.env')
from google.cloud import bigquery
import google.auth
import kagglehub
from kagglehub import KaggleDatasetAdapter
import ast

credentials, project_id = google.auth.default()

# Update the in-memory credentials cache (added in pandas-gbq 0.7.0).
pandas_gbq.context.credentials = credentials
pandas_gbq.context.project = "project-a87a976f-73e4-4a6c-9f9"


def get_tables_from_bq(table_refs):
    client = bigquery.Client(project = "project-a87a976f-73e4-4a6c-9f9")
    project = "project-a87a976f-73e4-4a6c-9f9"
    dataset_id = "GRAMMY_ANALYSIS"
    dataset_ref = bigquery.DatasetReference(project, dataset_id)
    # get reference tables from biquery
    dataframes = {}
    for ref in table_refs:
        table_ref = dataset_ref.table(ref)
        table = client.get_table(table_ref)
        dataframes[f"{ref}"] = client.list_rows(table).to_dataframe()
    return dataframes

dataframes = get_tables_from_bq(["UNIQUE_TRACKS_FROM_TRACK_AWARDS","UNIQUE_ALBUMS_FROM_ALBUM_AWARDS"])

SPOTIFY_SECRET = os.getenv('SPOTIFY_SECRET')
CELEBRITY_API_KEY=os.getenv('CELEBRITY_API_KEY')
NEWS_API_KEY=os.getenv('NEWS_API_KEY')

def request_token():
    try:
        response=requests.post(
            url="https://accounts.spotify.com/api/token",
            headers={"Content-Type":"application/x-www-form-urlencoded"},
            data={
                "grant_type":"client_credentials",
                "client_id":"4b9c57642fb541eba545ca8cbd551031",
                "client_secret": SPOTIFY_SECRET
                }
        )

        data=response.json()
        token=data["access_token"]

        return token

    except requests.exceptions.RequestException as e:
        raise e
    


def get_album_details(get_tables_from_bq, token):
    print("TOKEN RECEIVED:", token)
    album_details = []
    albums = get_tables_from_bq(['UNIQUE_ALBUMS_FROM_ALBUM_AWARDS'])['UNIQUE_ALBUMS_FROM_ALBUM_AWARDS']
    for row in albums.itertuples():
        d = {}
        if row.Artist:
            q=quote(f"album:{row.Winner} artist:{row.Artist}")
        else:
            q=quote(f"album:{row.Winner} year:{row.Year-2}-{row.Year+2}")
        try:
            response=requests.get(
                url=f"https://api.spotify.com/v1/search?q={q}&type=album",
                headers={"Authorization": f"Bearer {token}"}
            )

            # populate album details table with api response
            results = response.json()
            if response.status_code == 200 and "albums" in results:
                for result in results["albums"]["items"]:
                    if result['album_type'] == 'album':
                        d['Album'] = row.Winner
                        d['Artist'] = row.Artist
                        d['Album_ID'] = result["id"]
                        d['Album_Name'] = result["name"]
                        d['Total_Tracks'] = result["total_tracks"]
                        d['Release_Date'] = result["release_date"]
                
                        album_details.append(d)

            if response.status_code == 429:
                print("Spotify quota/rate limit reached")
                break

            else:
                print(f"Search failed for album for {row.Winner} - {row.Artist}")
                print(f"Status: {response.status_code}")
                print(f"Response: {results}")

            # update album UNIQUE_ALBUMS_FROM_ALBUM_AWARDS to populate artist field with artist from api response
            if row.Artist == None:
                if "albums" in results:
                    artists = []
                    for item in results["albums"]["items"]:
                        for artist in item["artists"]:
                            artists.append(artist["name"])
                            concatenated_artists = ", ".join(artists)
                            albums.loc[albums["Winner"] == row.Winner, "Artist"] = concatenated_artists
                elif response.status_code == 429:
                    print("Spotify quota/rate limit reached")
                    break
                else:
                    print(f"Search failed for artist for {row.Winner} - {row.Year}")
                    print(f"Status: {response.status_code}")
                    print(f"Response: {results}")

        except requests.exceptions.RequestException as e:
            raise e
    
    details_df = pd.DataFrame(album_details)

    try:
        pandas_gbq.to_gbq(details_df, 
                            "GRAMMY_ANALYSIS.SPOTIFY_ALBUMS", 
                            if_exists='replace')
        print('Successfully wrote dataframe SPOTIFY_ALBUMS to BigQuery')
    except:
        print('Failed to write dataframe SPOTIFY_ALBUMS to BigQuery')

def get_all_unique_artists(get_tables_from_bq):
    albums = get_tables_from_bq(["UNIQUE_ALBUMS_FROM_ALBUM_AWARDS"])["UNIQUE_ALBUMS_FROM_ALBUM_AWARDS"]
    tracks = get_tables_from_bq(["UNIQUE_TRACKS_FROM_TRACK_AWARDS"])["UNIQUE_TRACKS_FROM_TRACK_AWARDS"]
    frames = [albums,tracks]
    artists = pd.concat(frames)
    unique_artists =(artists[['Artist']].drop_duplicates().reset_index(drop=True))
    try:
        pandas_gbq.to_gbq(unique_artists, 
                            "GRAMMY_ANALYSIS.UNIQUE_ARTISTS", 
                            if_exists='replace')
        print('Successfully wrote dataframe UNIQUE_ARTISTS to BigQuery')
    except Exception as e:
        print('Failed to write dataframe UNIQUE_ARTISTS to BigQuery')
        print(f"Error: {e}")


def get_ids(df_column, no_of_ids, i):
    print('start_index: ',i,' end_index: ',i+no_of_ids)
    print('column slice: ',df_column[i:i+no_of_ids])
    return df_column[i:i+no_of_ids]

def get_tracks_from_albums(get_tables_from_bq, token):
    spotify_albums=get_tables_from_bq(['SPOTIFY_ALBUMS'])['SPOTIFY_ALBUMS']

    
    album_ids = spotify_albums['Album_ID'].unique()
    print("album_ids: ",album_ids)
    
    album_tracks = []
    for id in album_ids:

        try:
            response=requests.get(
                url=f"https://api.spotify.com/v1/albums/{id}/tracks",
                headers={"Authorization": f"Bearer {token}"}
            )
            print(f"Calling https://api.spotify.com/v1/albums/{id}/tracks")
            results = response.json()
            if response.status_code == 200:
                for item in results["items"]:
                    print(f"Adding track {item['name']}")
                    t = {}
                    t['Album_ID'] = id
                    t['Track_ID'] = item["id"]
                    t['Track_Name'] = item["name"]
            
                    album_tracks.append(t)

            elif response.status_code == 429:
                print("Spotify quota/rate limit reached")
                break

            else:
                print(f"Status: {response.status_code}")
                print(f"Response: {results}")

        except requests.exceptions.RequestException as e:
            raise e
        
    print('Fully populated album_tracks: ',album_tracks)
    # join to SPOTIFY ALBUMS df on album id and add columns track id and track name 
    album_tracks_df = pd.DataFrame(album_tracks)
    print("album_tracks_df: ", album_tracks_df.head())
    spotify_albums = spotify_albums.merge(album_tracks_df, on='Album_ID', how='left')
    print("spotify_albums: ",spotify_albums)


    try:
        pandas_gbq.to_gbq(spotify_albums , "GRAMMY_ANALYSIS.SPOTIFY_ALBUMS", if_exists='replace')
        print('Successfully wrote dataframe SPOTIFY_ALBUMS to BigQuery')
    except:
        print('Failed to write dataframe SPOTIFY_ALBUMS to BigQuery') 

def get_all_unique_tracks(get_tables_from_bq):
    spotify_albums=get_tables_from_bq(['SPOTIFY_ALBUMS'])['SPOTIFY_ALBUMS']
    album_fields=spotify_albums[['Track_Name','Track_ID','Artist']]

    track_awards=get_tables_from_bq(['UNIQUE_TRACKS_FROM_TRACK_AWARDS'])['UNIQUE_TRACKS_FROM_TRACK_AWARDS']
    track_awards=track_awards.rename(columns={
        'Winner':'Track_Name'
    })

    frames=[track_awards, album_fields]
    unique_tracks_from_all_awards=pd.concat(frames, ignore_index=True).drop_duplicates()

    try:
        pandas_gbq.to_gbq(unique_tracks_from_all_awards , "GRAMMY_ANALYSIS.UNIQUE_TRACKS_FROM_ALL_AWARDS", if_exists='replace')
        print('Successfully wrote dataframe UNIQUE_TRACKS_FROM_ALL_AWARDS to BigQuery')
    except:
        print('Failed to write dataframe UNIQUE_TRACKS_FROM_ALL_AWARDS to BigQuery') 


def get_track_details(get_tables_from_bq, token):
    tracks=get_tables_from_bq(['UNIQUE_TRACKS_FROM_ALL_AWARDS'])['UNIQUE_TRACKS_FROM_ALL_AWARDS']
    # where track id available, call search based on track id 
    track_details  =[]
    for row in tracks.itertuples():
        d = {}
        if row.Track_ID:
            try:
                response=requests.get(
                url=f"https://api.spotify.com/v1/tracks/{row.Track_ID}",
                headers={"Authorization": f"Bearer {token}"}
                )
                print(f"Calling https://api.spotify.com/v1/tracks/{row.Track_ID}")
                results = response.json()
                if response.status_code == 200:
                    print(f"Adding track {results['name']}")
                    d['Track_ID'] = row.Track_ID
                    d['Track_Name'] = row.Track_Name
                    d['Album_ID'] = results['album']['id']
                    d['Release_Date'] = results['album']['release_date']
                    d['Duration_ms'] = results['duration_ms']
                    d['Explicit'] = results['explicit']
                    d['Popularity'] = results.get('popularity')
                    d['Track_Number'] = results['track_number']
                
                    track_details.append(d)

                elif response.status_code == 429:
                    print("Spotify quota/rate limit reached")
                    break

                else:
                    print(f"Status: {response.status_code}")
                    print(f"Response: {results}")

            except requests.exceptions.RequestException as e:
                raise e
    # where not available, call search based on track name and artist 
        else:
            q=quote(f"track: {row.Track_Name} artist: {row.Artist}")
            try:
                response=requests.get(
                url=f"https://api.spotify.com/v1/search?q={q}&type=track",
                headers={"Authorization": f"Bearer {token}"}
                )
                print(f"Calling https://api.spotify.com/v1/search?q={q}&type=track")
                results = response.json()

                if response.status_code == 200:
                    for track in results['tracks']['items']:
                        print(f"Adding track {track['name']}")
                        d['Track_ID'] = track['id']
                        d['Track_Name'] = row.Track_Name
                        d['Album_ID'] = track['album']['id']
                        d['Release_Date'] = track['album']['release_date']
                        d['Duration_ms'] = track['duration_ms']
                        d['Explicit'] = track['explicit']
                        d['Popularity'] = track.get('popularity')
                        d['Track_Number'] = track['track_number']
                
                    track_details.append(d)

                elif response.status_code == 429:
                    print("Spotify quota/rate limit reached")
                    break

                else:
                    print(f"Status: {response.status_code}")
                    print(f"Response: {results}")

            except requests.exceptions.RequestException as e:
                raise e
    # create track details table out of results
    track_details_df = pd.DataFrame(track_details)
    print('track_details_df: ',track_details_df.head(10))
    
    try:
        pandas_gbq.to_gbq(track_details_df , "GRAMMY_ANALYSIS.SPOTIFY_TRACKS", if_exists='replace')
        print('Successfully wrote dataframe SPOTIFY_TRACKS to BigQuery')
    except:
        print('Failed to write dataframe SPOTIFY_TRACKS to BigQuery') 


def populate_unique_tracks_with_ids(get_tables_from_bq):
    track_details_df=get_tables_from_bq(['SPOTIFY_TRACKS'])['SPOTIFY_TRACKS']
    tracks=get_tables_from_bq(['UNIQUE_TRACKS_FROM_ALL_AWARDS'])['UNIQUE_TRACKS_FROM_ALL_AWARDS']

    # update Unique_Tracks_From_All_Awards with track ids 
    unique_tracks = tracks.merge(track_details_df, on='Track_Name',how='left', suffixes=('_u','_d'))
    unique_tracks['Track_ID']=unique_tracks['Track_ID_u'].fillna(unique_tracks['Track_ID_d'])
    unique_tracks=unique_tracks.drop(columns=['Track_ID_u',
                                'Track_ID_d',
                                'Album_ID',
                                'Release_Date',
                                'Duration_ms',
                                'Explicit',
                                'Popularity',
                                'Track_Number'])
    print('unique_tracks',unique_tracks.head(10))

    try:
        pandas_gbq.to_gbq(unique_tracks , "GRAMMY_ANALYSIS.UNIQUE_TRACKS_FROM_ALL_AWARDS", if_exists='replace')
        print('Successfully wrote dataframe UNIQUE_TRACKS_FROM_ALL_AWARDS to BigQuery')
    except:
        print('Failed to write dataframes UNIQUE_TRACKS_FROM_ALL_AWARDS to BigQuery') 

def get_track_audio_features():
    df = kagglehub.dataset_load(
    KaggleDatasetAdapter.PANDAS,
    "yamaerenay/spotify-dataset-19212020-600k-tracks",
    "tracks.csv"
    )

    df['artists'] = df['artists'].apply(ast.literal_eval).str.join('|')
    df['id_artists'] = df['id_artists'].apply(ast.literal_eval).str.join('|')

    try:
        pandas_gbq.to_gbq(df , "GRAMMY_ANALYSIS.AUDIO_DATASET", if_exists='replace')
        print('Successfully wrote dataframe AUDIO_DATASET to BigQuery')
    except:
        print('Failed to write dataframe AUDIO_DATASET to BigQuery') 
        print(pandas_gbq.to_gbq(df , "GRAMMY_ANALYSIS.AUDIO_DATASET", if_exists='replace'))

def get_artist_details(get_tables_from_bq, token):
    # call search using names in UNIQUE_ARTISTS
    unique_artists = get_tables_from_bq(['UNIQUE_ARTISTS'])['UNIQUE_ARTISTS']

    artists = []
    for row in unique_artists.itertuples():
        q=quote(f"artist: {row.Artist}")
        d = {}
        try:
            response=requests.get(
            url=f"https://api.spotify.com/v1/search?q={q}&type=artist",
            headers={"Authorization": f"Bearer {token}"}
            )
            print(f"Calling https://api.spotify.com/v1/search?q={q}&type=artist")
            results = response.json()

            if response.status_code == 200:
                for artist in results['artists']['items']:
                    print(f"Adding artist {artist['name']}")
                    d['Artist_ID'] = artist['id']
                    d['Artist_Name'] = row.Artist
                    d['Spotify_Artist_Name'] = artist['name']
                    d['Spotify_Followers'] = artist.get('followers',{}).get('total')
                    d['Artist_Popularity'] = artist.get('popularity')
            
                artists.append(d)

            elif response.status_code == 429:
                print("Spotify quota/rate limit reached")
                break

            else:
                print(f"Status: {response.status_code}")
                print(f"Response: {results}")

        except requests.exceptions.RequestException as e:
            raise e

    artist_details=pd.DataFrame(artists)
    print(artist_details.head(10))

    try:
        pandas_gbq.to_gbq(artist_details , "GRAMMY_ANALYSIS.SPOTIFY_ARTIST_DATA", if_exists='replace')
        print('Successfully wrote dataframe SPOTIFY_ARTIST_DATA to BigQuery')
    except:
        print('Failed to write dataframe SPOTIFY_ARTIST_DATA to BigQuery') 
        print(pandas_gbq.to_gbq(artist_details , "GRAMMY_ANALYSIS.SPOTIFY_ARTIST_DATA", if_exists='replace'))

def call_celebrity_api(get_tables_from_bq, CELEBRITY_API_KEY):
    artists = get_tables_from_bq(['UNIQUE_ARTISTS'])['UNIQUE_ARTISTS']
    celebrities=[]
    for row in artists.itertuples():
        artist = quote(f"{row.Artist}")
        try:
            response = requests.get(
                url=f"https://api.api-ninjas.com/v1/celebrity?name={artist}",
                headers={'X-Api-Key':CELEBRITY_API_KEY}
            )
            result = response.json()

            if response.status_code==200:
                for celeb in result:
                    if row.Artist and celeb['name']==row.Artist.lower():
                        print('celeb: ',celeb['name'], ' ',celeb.get('occupation'))
                        celebrities.append(celeb)

            elif response.status_code == 429:
                print("Error:", response.status_code, result)
                break
                
            else:
                print("Error:", response.status_code, response.text)
        
        except requests.exceptions.RequestException as e:
                raise e
        
    df=pd.DataFrame(celebrities)
    print(df.head(10))

    try:
        pandas_gbq.to_gbq(df , "GRAMMY_ANALYSIS.ARTIST_DATA", if_exists='replace')
        print('Successfully wrote dataframe ARTIST_DATA to BigQuery')
    except:
        print('Failed to write dataframe ARTIST_DATA to BigQuery') 
        print(pandas_gbq.to_gbq(df , "GRAMMY_ANALYSIS.ARTIST_DATA", if_exists='replace'))

def get_headlines(get_tables_from_bq, NEWS_API_KEY):
    artists = get_tables_from_bq(['UNIQUE_ARTISTS'])['UNIQUE_ARTISTS']
    headlines = []

    for row in artists.itertuples():
        artist = quote(f"{row.Artist}")
        try:
            response = requests.get(
                url=f"https://newsapi.org/v2/top-headlines?q={artist}&pageSize=5",
                headers={'X-Api-Key':NEWS_API_KEY}
            )
            result = response.json()

            if response.status_code==200:
                for headline in result['articles']:
                    d = {}
                    d['Source'] = headline['source']['name']
                    d['Author'] = headline['author']
                    d['Title'] = headline['title']
                    d['Description'] = headline['description']
                    d['Url'] = headline['url']
                    d['Published_At'] = headline['publishedAt']

                    headlines.append(d)

            elif response.status_code == 429:
                print("Error:", response.status_code, result)
                break
                
            else:
                print("Error:", response.status_code, result)
        
        except requests.exceptions.RequestException as e:
                raise e
        
    df=pd.DataFrame(headlines)
    print(df.head(10))

    try:
        pandas_gbq.to_gbq(df , "GRAMMY_ANALYSIS.TOP_HEADLINES", if_exists='replace')
        print('Successfully wrote dataframe TOP_HEADLINES to BigQuery')
    except:
        print('Failed to write dataframe TOP_HEADLINES to BigQuery') 
        print(pandas_gbq.to_gbq(df , "GRAMMY_ANALYSIS.TOP_HEADLINES", if_exists='replace'))

if __name__=="__main__":
    # token=request_token()
    # get_album_details(get_tables_from_bq, token)
    # get_all_unique_artists(get_tables_from_bq)
    # get_tracks_from_albums(get_tables_from_bq, token)
    # get_all_unique_tracks(get_tables_from_bq)
    # get_track_details(get_tables_from_bq, token)
    # populate_unique_tracks_with_ids(get_tables_from_bq)
    # get_track_audio_features()
    # get_artist_details(get_tables_from_bq, token)
    # call_celebrity_api(get_tables_from_bq, CELEBRITY_API_KEY)
    get_headlines(get_tables_from_bq, NEWS_API_KEY)