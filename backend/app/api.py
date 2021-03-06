import re
from fastapi import FastAPI, Body, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
import joblib
import warnings   
warnings.filterwarnings("ignore")

from logging.config import dictConfig
import logging
from app.config import LogConfig

dictConfig(LogConfig().dict())
logger = logging.getLogger("pmds")


from app.models import RequestBody, ResponseBody
from app.helper import (
    feature_engineering, 
    parse_request,
    parse_input,
    predict_score,
    grade_binning)

# initialize the fastapi app
app = FastAPI()

# mount templates and static folder with Jinja
templates = Jinja2Templates(directory='./frontend/templates/')
app.mount("/statics", StaticFiles(directory="./frontend/statics"), name="statics")

# add logging for invalid request error 
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    content_log=jsonable_encoder({"detail": exc.errors(), "body": exc.body})
    content_msg =  content_log.get("detail")[0].get("msg")  # only get the message
    content_loc = content_log.get("detail")[0].get("loc")[1]  # get the error field
    logger.error(content_log)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=content_msg + ", field : " + content_loc
    )

# add CORS middleware
origins = [
    "http://localhost:3000",
    "localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Load model at the first instance of app initializaton
try :
    # for uvicorn
    model_bureau = joblib.load("backend/assets/xgb_retrain_bureau.pkl")
    model_no_bureau = joblib.load("backend/assets/xgb_retrain_no_bureau.pkl")

    # for gunicorn
    # model_bureau = joblib.load("./assets/xgb_retrain_bureau.pkl")
    # model_no_bureau = joblib.load("./assets/xgb_retrain_no_bureau.pkl")
    print("Model Loaded")
except:
    print("Fail to Load Model")

@app.get("/")
async def root():
    """
    Root endpoint
    """
    url = app.url_path_for("index_html")
    response = RedirectResponse(url=url)
    logger.debug("Redirected to home")
    return response

@app.get('/home')
def index_html(request: Request):
    """
    Endpoint for the loan application form
    """
    return templates.TemplateResponse('index.html', context={'request': request})

@app.post("/predict")
async def get_prediction(request: Request):
    """
    Calculating and doing prediction
    """
    reqDataForm = await request.form()
    reqData = jsonable_encoder(reqDataForm)
    reqData_parsed = parse_request(reqData)

    t = feature_engineering(parse_input(reqData_parsed))
    if reqData.get("bureau"):
        score, proba, loan_dec = predict_score(t, model_bureau)
        grade = grade_binning(proba, 'model_bureau')
    else:
        score, proba, loan_dec = predict_score(t, model_no_bureau)
        grade = grade_binning(proba, 'model_no_bureau')

    if grade in ['A', 'B'] :
        page = 'result_approve.html'
    else:
        page = 'result_reject.html'
    logger.info(f"predicting..{score}")
    logger.info(f"Loan Decision..{loan_dec}")

    return templates.TemplateResponse(page, context={'request': request, 'grade': grade})

@app.post("/apiTest", response_model=ResponseBody)
async def testing(
    req: RequestBody = Body(
    ..., 
    examples = {
            "bureaufound" : { # example of payload with bureau data available
                "summary" : "payload with bureau data",
                "description" : "Input example for customer with bureau data available.",
                "value" : {
                    "age": 20,
                    "income": 1000000,
                    "gender": "Male",
                    "hasApplied": "Yes",
                    "hasIncome": "Yes",
                    "education": "Diploma",
                    "purpose": "Working Capital",
                    "bureau": {"loanWithDelay" : 0, "loanNoDelay" : 0}
                }
            },
            "nobureau" : { # example of payload without bureau data
                "summary" : "payload without bureau data",
                "description" : "Example of request if customer does not have bureau data available.",
                "value" : {
    
                    "age": 22,
                    "income": 2000000,
                    "gender": "Female",
                    "hasApplied": "No",
                    "hasIncome": "Yes",
                    "education": "Bachelor Degree",
                    "purpose": "Investment",
                    "bureau": None
                }
            }
        } )
    ):
    """
    Endpoint to test the post request for prediction

    """

    # cast request body to dict
    req_dict = req.dict()
    t = feature_engineering(parse_input(req_dict))
    if req_dict.get("bureau"):
        score, proba, loan_dec = predict_score(t, model_bureau)
    else:
        score, proba, loan_dec = predict_score(t, model_no_bureau)
    logger.info(f"predicting..{score}")
    return {"LoanDecision" : loan_dec}
