# DO NOT run this script directly.
# It is sent to the server and run by setup_upload inside web2py (-S OZtree -M -R).

import os

username = os.environ["UPLOAD_USER"]
password = os.environ["UPLOAD_PASSWORD"]

hashed = db.auth_user.password.validate(password)[0]
user = db(db.auth_user.username == username).select().first()
if user:
    user.update_record(password=hashed, registration_key="")
else:
    user = auth.register_bare(
        first_name="Tour",
        last_name="Uploader",
        username=username,
        email="%s@onezoom.org" % username,
        password=password,
    )
    if not user:
        raise RuntimeError("Failed to create user %s" % username)
    db(db.auth_user.id == user.id).update(registration_key="")
db.commit()
print("Created or updated web2py user %s" % username)
