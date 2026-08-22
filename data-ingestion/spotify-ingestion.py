import requests

import os
from dotenv import load_dotenv
load_dotenv(dotenv_path='./.env')

SPOTIFY_SECRET = os.getenv('SPOTIFY_SECRET')

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
        print(token)

        return token

    except requests.exceptions.RequestException as e:
        raise e
    


def get_artist(artist_id, token):
    try:
        response=requests.get(
            url=f"https://api.spotify.com/v1/artists/{artist_id}",
            headers={"Authorization": f"Bearer  {token}"}
        )

        return response.json()

    except requests.exceptions.RequestException as e:
        raise e


    
if __name__=="__main__":
    token=request_token()
    get_artist('4iHNK0tOyZPYnBU7nGAgpQ',token)

