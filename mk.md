To create database migrations with SQLModel, you use Alembic, a lightweight migration tool for SQLAlchemy. Since SQLModel is built on top of SQLAlchemy, it integrates directly with Alembic's workflow. [1, 2, 3, 4, 5] 
## 1. Install Required Packages [6] 
Ensure you have both sqlmodel and alembic installed in your environment. [7] 

pip install sqlmodel alembic

## 2. Initialize Alembic
Run the following command in your project's root directory to create the migration environment. [8, 9] 

alembic init migrations

This generates an alembic.ini file and a migrations/ directory containing env.py and a versions/ folder. [8] 
## 3. Configure alembic.ini
Update the database connection string in your alembic.ini file to match your project's database URL. [9, 10] 

# Example for SQLite
sqlalchemy.url = sqlite:///./database.db

## 4. Configure env.py for SQLModel [11, 12] 
Alembic needs to know about your SQLModel metadata to track schema changes. You must modify migrations/env.py to import your models and point target_metadata to SQLModel.metadata. [8, 13] 

   1. Import SQLModel and your models:
   
   from sqlmodel import SQLModelfrom app.models import *  # Ensure all your models are imported
   
   2. Set the metadata:
   
   # Find this line and update ittarget_metadata = SQLModel.metadata 
   
   [14, 15, 16] 

Users on [Stack Overflow](https://stackoverflow.com/questions/68932099/how-to-get-alembic-to-recognise-sqlmodel-database-model) and [GitHub](https://github.com/fastapi/sqlmodel/issues/85) recommend ensuring all model files are explicitly imported so that they are registered with the metadata. [8, 10, 17] 
## 5. Update script.py.mako
To ensure generated migration files recognize SQLModel types, add import sqlmodel to your migrations/script.py.mako template. [10, 13] 

import sqlalchemy as saimport sqlmodel  # Added for SQLModel support

## 6. Generate and Apply Migrations
Once configured, you can automatically detect schema changes and apply them to your database. [1, 18] 

* Generate a migration script:

alembic revision --autogenerate -m "Initial migration"

* Apply the migration:

alembic upgrade head

[19, 20, 21] 

For a more in-depth walkthrough, you can follow this SQLModel & Alembic Tutorial on [DEV Community](https://dev.to/mchawa/sqlmodel-alembic-tutorial-gc8). [22] 
Would you like to see how to handle asynchronous migrations if you are using an async database driver?

[1] [https://www.amitavroy.com](https://www.amitavroy.com/articles/database-migrations-with-python-why-alembic-sqlmodel-is-the-perfect-combo)
[2] [https://python.plainenglish.io](https://python.plainenglish.io/database-migrations-in-python-a-comprehensibe-guide-for-developers-8b13837ce4ce#:~:text=Alembic%20Alembic%20is%20a%20lightweight%20database%20migration,simplicity%2C%20flexibility%2C%20and%20compatibility%20with%20multiple%20databases.)
[3] [https://www.linkedin.com](https://www.linkedin.com/pulse/mapping-pydantic-models-sqlalchemy-other-orm-alembic-herman-varzari-fnspf#:~:text=Alembic%20is%20a%20lightweight%20database%20migration%20tool,database%20schema%20over%20time%2C%20allowing%20you%20to:)
[4] [https://www.amitavroy.com](https://www.amitavroy.com/articles/database-migrations-with-python-why-alembic-sqlmodel-is-the-perfect-combo#:~:text=Why%20SQLModel%20and%20Alembic%20are%20a%20Perfect,an%20incredibly%20streamlined%20workflow%20for%20database%20migrations.)
[5] [https://sqlmodel.tiangolo.com](https://sqlmodel.tiangolo.com/databases/#:~:text=SQLModel%20is%20built%20on%20top%20of%20SQLAlchemy.,mixed%20together%20with%20some%20sugar%20on%20top.)
[6] [https://sqlmodel.tiangolo.com](https://sqlmodel.tiangolo.com/databases/#:~:text=SQLModel%20is%20built%20on%20top%20of%20SQLAlchemy.,mixed%20together%20with%20some%20sugar%20on%20top.)
[7] [https://arunanshub.hashnode.dev](https://arunanshub.hashnode.dev/using-sqlmodel-with-alembic#:~:text=Installing%20Alembic%20and%20SQLModel%0A%0AInstall%20alembic%20and%20SQLModel,poetry%20shell%20before%20executing%20any%20Alembic%20command.)
[8] [https://stackoverflow.com](https://stackoverflow.com/questions/68932099/how-to-get-alembic-to-recognise-sqlmodel-database-model)
[9] [https://medium.com](https://medium.com/@_rajendrayadav/alembic-with-sqlmodel-and-fastapi-a302ec10e079)
[10] [https://github.com](https://github.com/fastapi/sqlmodel/issues/85)
[11] [https://github.com](https://github.com/fastapi/sqlmodel/issues/85#:~:text=Now%20all%20you%20have%20to%20do%20is,all%20your%20model%20will%20be%20already%20registred.)
[12] [https://dev.to](https://dev.to/mchawa/sqlmodel-alembic-tutorial-gc8)
[13] [https://arunanshub.hashnode.dev](https://arunanshub.hashnode.dev/using-sqlmodel-with-alembic)
[14] [https://github.com](https://github.com/fastapi/sqlmodel/issues/85#:~:text=I%20hope%20I%27m%20not%20too%20late%2C%20but,and%20import%20SQLModel%20in%20that%20same%20file.)
[15] [https://www.youtube.com](https://www.youtube.com/watch?v=pRYzMF04fLw)
[16] [https://testdriven.io](https://testdriven.io/blog/fastapi-sqlmodel/)
[17] [https://tobydevlin.com](https://tobydevlin.com/blog/database-migration-with-sqlmodel-and-alembic/)
[18] [https://adex.ltd](https://adex.ltd/database-migrations-with-alembic-and-fastapi-a-comprehensive-guide-using-poetry)
[19] [https://www.amitavroy.com](https://www.amitavroy.com/articles/database-migrations-with-python-why-alembic-sqlmodel-is-the-perfect-combo)
[20] [https://github.com](https://github.com/sqlalchemy/alembic/discussions/1046#:~:text=I%20have%20an%20existing%20database%20that%20I,creation%20of%20each%20table%20in%20my%20database.)
[21] [https://python.plainenglish.io](https://python.plainenglish.io/database-migrations-in-python-a-comprehensibe-guide-for-developers-8b13837ce4ce#:~:text=Remember%20to%20run%20the%20alembic%20upgrade%20head,your%20database%20up%20to%20the%20latest%20version.)
[22] [https://dev.to](https://dev.to/mchawa/sqlmodel-alembic-tutorial-gc8)
