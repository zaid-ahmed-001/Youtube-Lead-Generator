import werkzeug.security as security

USERS_DB = {
    "admin": {
        "username": "admin",
        "name": "System Administrator",
        "password_hash": security.generate_password_hash("admin123"),
        "role": "Admin"
    },
    "analyst": {
        "username": "analyst",
        "name": "Lead Intelligence Analyst",
        "password_hash": security.generate_password_hash("analyst123"),
        "role": "Analyst"
    },
    "viewer": {
        "username": "viewer",
        "name": "Executive Viewer",
        "password_hash": security.generate_password_hash("viewer123"),
        "role": "Viewer"
    }
}

ROLE_HIERARCHY = {
    "Admin": 3,
    "Analyst": 2,
    "Viewer": 1
}

class AuthService:
    @staticmethod
    def authenticate(username, password):
        user = USERS_DB.get(username.lower().strip())
        if user and security.check_password_hash(user["password_hash"], password):
            return {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }
        return None

    @staticmethod
    def has_permission(user_role, required_role):
        user_level = ROLE_HIERARCHY.get(user_role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 0)
        return user_level >= required_level

    @staticmethod
    def get_users_list():
        return [{"username": u["username"], "name": u["name"], "role": u["role"]} for u in USERS_DB.values()]
