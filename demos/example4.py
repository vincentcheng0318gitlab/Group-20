"""Check misspellings in class methods, instance attributes, and loop comprehensions."""

class UsrAccaunt:

    def __init__(self, usernaam: str, passwrd_hash: str):
        self.usernaam = usernaam
        self.passwrd_hash = passwrd_hash

    def validat_creds(self, entred_pass: str) -> bool:
        is_match = self.passwrd_hash == entred_pass
        return is_match


def get_actv_users(usrs_list):
    filterd_usrs = [u for u in usrs_list if u != "admin"]
    return filterd_usrs
