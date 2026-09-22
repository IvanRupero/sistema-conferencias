from locust import HttpUser, task, between

class AsistenteUser(HttpUser):
    host = "http://127.0.0.1:5000"  # <--- Agrega esta línea aquí
    wait_time = between(1, 2)

    @task
    def index(self):
        self.client.get("/registro/1")