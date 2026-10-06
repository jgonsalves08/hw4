# AI Prompts — HW4

Prompts used with the AI assistant for each problem. Each section lists the initial prompt and, if one was needed, a follow-up prompt plus a sentence on what the first attempt was missing.

---

## Problem 2 - Analyze the database

**Initial prompts:**

1. Explore the database schema:

> Ok moving on to Problem 2. I'd like to look at the campus_customs.db database in order for me to understand the fields used within the tables. Some of the most important fields I need to understand are catalogue, inventory, and users, but it would be good to understand them all

2. Create the harness file:

> Can you create the harness.md file and put it under a new folder called output. This is a file that we will also keep adding onto throughout this homework, but for now put the each table, its fields, and a one sentence liner on why each field matters for the shop or for the chatbot

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 3 - Build the Campus Customs website

**Initial prompt:**

> Ok moving on to Problem 3. We need to build the front end web app for Campus Customs (using React + Vite + TypeScript). There should be a navigation bar at the top of the webpage that links to the following pages: Home, Products, About Us, Log in, and Create Account. Pull the Campus Customs-style wording from [yalebulldogblue.com](https://yalebulldogblue.com/), but I will need to write the pages in my own voice/wording. So once I see what it looks like, I will update the pages. For the Products page, I'd like to see the product images from the catalogue (you can use the image paths from our campus_customs database) with the product info (name, price, and short description). Each product should open a single-item page. This single-item page should have the large image on one side, full product text on the other which should include the description, price, sizes and stock amount when we have them. Clicking a card on the Products page should take the individual to the single-item page. Then lastly, I would like a chat interface in the bottom right hand side of the web app site (it can be a floating chat panel). For now the chat interface can just be a stub that will call the backend later. For now, create a FastAPI app in backend/main.py to serve products and images (later I will make it into a agent backend in a later problem).

**Follow-up prompt (if needed):**

> Before we move on, set up a virtual environment (.venv) for the backend and add a requirements.txt with the Python packages it needs so the project can be rebuilt. Also make sure the backend only serves the product images and nothing else from the data folder — the database file with users' password hashes should never be downloadable. Test that the images still load and that the database can't be reached.

- **`requirements.txt`**: lists the backend's Python dependencies (`fastapi`, `uvicorn[standard]`) so the environment can be rebuilt.
- **`.venv`**: a project virtual environment in HW4 with those dependencies installed, keeping them separate from the system Python.
- **Security fix**: the first version of the backend mounted the whole `data/` folder at `/images`, which let anyone download `campus_customs.db` (including user password hashes) at `/images/campus_customs.db`. The fix mounts only `data/products/` at `/images/products`; afterward the database URL, including a `../` path-traversal attempt, returns 404 while product images still load.

**What was lacking after the first prompt:** The first prompt didn't ask for a Python environment or dependency file to run the FastAPI backend, and didn't say which files the backend should keep private, so the first image route exposed the database.

---

## Problem 4 - Create account and login

**Initial prompts:**

1. Account and login requirements:

> Ok moving on to Problem 4. Now we need to create a normal create-account / login flow. For Create Account it should include: First Name, Last Name, Email, Password (and a confirm password). Then Log in would be just email and password. All new accounts should go into the users table in the database. These passwords should be stored securely so all hackers (both human or AI) can not access them. I should be able to use the test user that is already in the database to log in, and I'll create a new one as well. Then the output/harness.md should be updated with how auth works which should show what we store for a user and how the passwords are protected.

2. Narrowed scope:

> Just create the create account flow and the log in flow. I will check the rest

3. Document auth in the harness:

> Now update harness.md with how auth works

**Follow-up prompt (if needed):**

> Ok I tried to log in with the test email (using the test password), but it didn't work. So I'm assuming the iterations number is incorrect

**What was lacking after the first prompt:** The seed accounts' password hashes don't store their PBKDF2 iteration count, so the first version guessed a default and rejected the test user's correct password; we then used the known test account to find the right number of iterations.

---

## Problem 5 - PydanticAI agent backend

**Initial prompt:**

> Ok moving on to Problem 5. Now I would like to build up the shop chatbot as a PydanticAI agent behind the fastAPI. This is the chatbot we started in the front-end chat widget. The API app should be put in the main.py file in the backend folder. The file is run with Uvicorn. The agent should have the following four files:
>
> * backend/prompts/prompt.md - this is the system prompt (that we will continue adding to throughout the hw)
> * backend/agent.py - This is the agent entry and wiring file
> * backend/tools.py - This contains the tools the agent is able to call
> * backend/models.py - This should have the Pydantic / PydanticAI structured types
>
> Within the main.py file, there should be a chat route so a message from the website will cause the agent to reply. The model should be gpt-5.6-luna via Portkey, the PORTKEY_API_KEY should be pulled from .env and we should also use pydantic-ai-slim[openai]. The campus customs voice and safety basics should be put into prompts/prompt.md. And in harness.md make sure to describe how the front end talks to FastAPI and how the agent is loaded (including the prompt file and model). The backend should be able to run from the backend/ folder using the terminal command: uvicorn main:app --reload --port 8000

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 6 - Tools: product info and stock

**Initial prompt:**

> Ok moving on to Problem 6. I'd like to give the agent more tools, including allowing it to look up real information within the campus_customs.db database. This should include the product description, price, and how many of the product are in stock (which should be by size if the customer asks). The agent should NOT be inventing any prices or quantities, it must use the database when answering those types of questions. And if a size is out of stock, it should say it's out of stock. Update the prompt.md file so the agent knows to call these tools for any price or stock questions. And add/update the return types in models.py file too. Within the harness.md file, list out the tools and describe/explain which model fields we chose for the lookup result and why

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 7 - Chat search that updates the page

**Initial prompt:**

> Ok moving on to Problem 7. Now I'd like to add a new feature to the web site. When a customer asks about a type of item (like "what hoodies do you have?"), the agent should be able to search the catalogue and the website should dynamically show those matching items as product cards. These product cards should include: image, name, price, and short info on the product. When the dynamic product cards are loaded by this new feature, the same single-item page behavior from Problem 3 should still work (so including the new product cards put on the page by the chat should still open that detail view of the large image and full information when clicked). Also update the prompt.md and harness.md files so it is clear how the search results reach the page.

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 8 - Customer memory

**Initial prompt:**

> Ok moving on to Problem 8. If a shopper is logged in, their chat history with the agent should be saved in the database in an appropriate table and reload it when they return/log back in. The agent should know who is chatting with them (their name and email) and that should be put in the agent deps and or tolls the agent can call. Make sure to have enough page context going to the agent so if someone is asks something like "do you have this in pink" and they are on a product page, the agent knows which item the individual is referring to. The hint given was that you can put code into the agent context. Guests are still allowed to chat with the agent, but history will only need to be kept for those users that have logged in. Within the harness.md file make sure to put in how the user history is stored, what customer fields the agent can see and how page context is passed to the agent

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 9 - Usability improvements

**Initial prompt:**

> On to problem 9. Ok now we need to implement 2 front end usability imrpovements and 2 agent/backend usability improvements. These should be things that make the site look better/easier to use (front end) or make the agent output better/accurate/safer to use. These improvements should be written into a new md file, usability.md which should be put in the output folder. For each of the improvements it should write in the file what was added and why it helps a campus customs shopper or the business. These are what I'm thinking:
>
> Front End
>
> * When you hover over the Products button on the web page, it should show a general breakdown of the products available OR when you go into the products tab there should be a filter button where you can filter for general products. When I refer to general products I mean like Hoodie, T Shirt, Quarter Zip, etc. This will allow the users to get a better understand of what is available within the catalogue. Of course when they click onto the filter (like T-Shirts), the product cards should also be filtered.
> * Also within the products tab, there should be a price filter ranging from our least expensive products to our most expensive products (the range should be a line bar or something with 2 endpoints where they can toggle what range they want to see). And when they select the range, it should filter the products to that range. This would help individuals see only items within their range window/price point.
>
> Agent / Back End
>
> * I'd like the agent to have the ability to share what is the most popular product by looking at the chat history from other users. So for example, if someone asks "What is the most popular hoodie?", the agent should have tool to look at all users chat history and return which hoodie has been asked about the most
> * For the chatbot conversation history (chat_messages table), add a field that keeps track of the products asked/mentioned within the chat, so we get a better understanding later on what type of products are being asked about

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 10 - Style the website

**Initial prompt:**

> Ok on to Problem 10. I need to make the site look more like a real campus customs website. So I'd like to spruce it up a bit and make it look better as a whole (colors, motion, fonts, product presentation, the chat feel). Take a look at the picture I've attached, I like how the product types (categories on the picture) are broken out on the left side, along with the price filter range and other things, while the actual product picture and description take up most of the middle/right and pops out. I additionally like the ability to like (heart) the products you like. Let's start of with that and see how it looks (keep the blue and white color for now, maybe use a better font to make things look better)
>
> *(Attached: screenshot of a reference plant-shop storefront with a left filter sidebar, large product cards, and heart buttons.)*

**Follow-up prompt (if needed):**

> Can you make the categories and color options on the left multi-select. And once that's done, create a file called design.md in the output file and write down was changed (so everything that was added from the beginning of problem 10) and why it should help customers stick around and buy. This should be short and concrete

**What was lacking after the first prompt:** Categories and colors could only be filtered one at a time, so shoppers couldn't compare across types or colors, and the design changes weren't yet written up with how they help customers stay and buy.

**Follow-up prompt 2:**

> So for the color tag, it should only be the color of the product (like the shirt color or hoodie color) not all the colors within the picture/product (like the logo or the words on the product). Can you update that so when selecting certain colors it does it accurately?

**What was lacking:** The color filter matched any color listed for a product, including logo and lettering colors, so picking "Red" or "White" showed navy and gray shirts that only had red or white logos.

**Follow-up prompt 3:**

> Great and lastly for the chatbot agent, it currently shows data from previous chat history which I like however I would like to have the option of not seeing the chat history and start with a new chat history if possible (I'd also like it to show the date of the chat so the individual can remember when they were chatting with the chatbot).

**What was lacking:** All of a customer's messages were treated as one continuous chat, so there was no way to start fresh or tell when earlier messages were sent.

**Follow-up prompt 4:**

> I like that feature of seeing past chats or creating a new chat. Can you just add some text boxes that appear over the new chat button, past chats button, and close button when you hover each button on the chatbot window? Currently, it's hard to tell what each button does

**What was lacking:** The new chat-header buttons were icon-only (+, clock, ×), so shoppers couldn't tell what each one did without clicking it.

**Follow-up prompt 5:**

> Can you make the background grey color a little more vibrant? It seems a little bland currently (of the website)

**What was lacking:** The page background was a flat, near-white gray that looked bland and didn't reinforce the Yale-blue brand.

---

## Problem 11 - Site testing (app check)

**Initial prompt:**

> Ok moving on to Problem 11. So now we need to test the web site and document it in a new html file, app_check.html, that should be put in the output folder. This file you should be able to double click and open and it should include clear screenshots and short captions for 3 things:
>
> 1. The chat checking the inventory level of an item (which should be a true stock amount and price from the database)
> 2. The dynamic search-result cards appearing after a category question (for example asking for hoodies)
> 3. One of the usability features added in Problem 9
>
> Since this is something the homework graders will be grading, the html file should be easy to grade. This means there should be a header for each of those 3 captions, a screenshot for each, and one to two sentences on what the screenshot is showing. These screenshots image files should be put in output/app_check_images/ file path and then should be linked in the app_check.html with relation paths (for example app_check_images/inventory.png)

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.

---

## Problem 12 - Audit trail, safety, finish harness

**Initial prompt:**

> Ok moving on to Problem 12. I'd like to keep an append-only json file, audit_trail.json, within the output folder of agent-loop activity. This should include time, tool name, short args/result, and stop reason. This should not be wiped between runs. Also lets give some safety rules to the agent and we need to put them in the prompt.md file (like never pulling sensitive personal details/passwords, loop limits, etc). Then finish up the harness.md file so it's clear how the entire system works. This should include the model fields in the models.py file and why they were chosen, the tools and their abilities, all the safety rules, and any additional specs (including loop limits, any result caps, models, and how to run front and back ends)

**Follow-up prompt (if needed):**

> Within the harness.md file, if there were some information added from previous problem numbers (like a certain section), just make sure to note that within each section

**What was lacking after the first prompt:** The reorganized harness grouped everything by topic, so it no longer showed which problem each section, tool, model, safety rule, or limit came from.

---

## Problem 13 - Push to GitHub and submit the URL

**Initial prompt:**

> Great. On to Problem 13, first remove in TBD from previous sections in the AI_prompts.md file (they no longer need to be TBD). Then I need to put this code in a folder called hw4 and push it to a public GitHub repository (using my GitHub account). I will need the repo URL as that is what I will be submitting. The folder layout should look like the expected file layout in the picture. The .env.example is an example (NOT MY REAL .env file) and it should just include placeholders. Additionally, the campus_customs.db or product images should not be put in the GutHub repo either. Should use .gitignore. Then the local only data pack should be like in the picture too (which should not be put in git). The agent is the prompts.md, agent.py, tools.py, and models.py under backend/ and the README.md should explain how to run the front end and back end after placing the data pack.
>
> *(Attached: the expected `hw4/` file layout and the local-only `data/` pack layout.)*

**Follow-up prompt (if needed):**

> Not needed.

**What was lacking after the first prompt:** Nothing — no follow-up was needed.
