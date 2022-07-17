## livetweets

Requirements:  
Docker  
Twitter API 2.0 Bearer Token

To use:
1. Clone the repository
2. Edit `backend\web-back\.env` file to add the Twitter API bearer token and Django secret key.
3. Build the containers by running `docker-compose build`
4. Migrate the database by running `docker-compose run --rm web-back sh -c "python manage.py migrate"`
5. Create a django superuser by running `docker-compose run --rm web-back sh -c "python manage.py createsuperuser"`
6. Start the app by running `docker-compose up`

The app should now be running on port 80. 
