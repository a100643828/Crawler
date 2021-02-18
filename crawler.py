# -*- coding: utf-8 -*-
"""crawler.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1gYH9-YVR-NsDXBwuJQAEqC9NscwsHVDF
"""

import mysql.connector
from mysql.connector import Error
from pytz import timezone
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import json
from lxml import html

CanRun = True

email = None
password = None
apr_low = None
apr_high = None
income = None
C_STU_NPR = True

monthInvest = {
    'month_rest_day': None,
    'month_total_amount': None,
    'order_amount': None,
    'month_remain': None,
    'last_rest_day': None
}

keywords = []

today = datetime.now(timezone('Asia/Taipei'))

backed = []


def GetInfo():
    global CanRun, email, password, apr_low, apr_high, income, C_STU_NPR, monthInvest, keywords, today, backed
    try:
        connection = mysql.connector.connect(host='localhost',
                                             database='lnbcrawler',
                                             user='root',
                                             password='root')
        sql_select_Query = """select * from month_invest"""
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute(sql_select_Query)
            records = cursor.fetchall()
            if(len(records) == 1):
                records = records[0]
                monthInvest['month_rest_day'] = records[0]
                monthInvest['month_total_amount'] = records[1]
                monthInvest['order_amount'] = records[2]
                monthInvest['month_remain'] = records[3]
                monthInvest['last_rest_day'] = records[4]
                if(monthInvest['month_remain'] < monthInvest['order_amount']):
                    CanRun = False
                    return
                if(today.day == monthInvest['month_rest_day'] and today.date() != monthInvest['last_rest_day']):
                    sql = "update month_invest set month_remain={}, last_rest_day='{}'".format(
                        monthInvest['month_total_amount'], datetime.now(timezone('Asia/Taipei')).strftime('%Y-%m-%d'))
                    cursor.execute(sql)
                    connection.commit()
            else:
                CanRun = False
                return

            sql_select_Query = "select * from input"
            cursor.execute(sql_select_Query)
            records = cursor.fetchall()
            if(len(records) == 1):
                records = records[0]
                email = records[0]
                password = records[1]
                apr_low = int(records[2])
                apr_high = int(records[3])
                income = int(records[4])
                C_STU_NPR = records[5] == 1
            else:
                CanRun = False
                return

            sql_select_Query = "select * from keywords"
            cursor.execute(sql_select_Query)
            keywords = [item[0] for item in cursor.fetchall()]
            sql_select_Query = "select back_item from back_serial_log"
            cursor.execute(sql_select_Query)
            backed = [item[0] for item in cursor.fetchall()]
        else:
            CanRun = False
    except Error as e:
        CanRun = False
    finally:
        if (connection.is_connected()):
            cursor.close()
            connection.close()
            print("GetInfo Over")


def Crawler():
    global CanRun, email, password, apr_low, apr_high, income, C_STU_NPR, monthInvest, keywords, today, backed
    if(CanRun == False):
        return
    session_requests = requests.session()
    result = session_requests.get("")
    tree = html.fromstring(result.text)
    authenticity_token = list(
        set(tree.xpath("//input[@name='_token']/@value")))[0]
    payload = {
        "_token": authenticity_token,
        "email": email,
        "password": password
    }
    login_result = session_requests.post(
        "", data=payload, headers=dict(referer=""))
    result = session_requests.get(
        "", headers=dict(referer=""))

    # 撈案子(以利率排序最高前100筆)
    caseResult = session_requests.get(
        "")
    case = json.loads(caseResult.text)['data']
    # 撈出滿足條件的案子
    # 創業者
    case = [x for x in case if x['purpose'] != '創業']
    # 期數
    case = [x for x in case if int(x['period']) > 30]
    # 學霸
    output_dict = [x for x in case if x['back_status'] == 'can_back']
    output_dict = [
        x for x in output_dict if C_STU_NPR and x['credit_level'] == 'C_STU_NPR']

    output_dict2 = [x for x in case if x['back_status'] == 'can_back']
    # 利率
    output_dict2 = [x for x in output_dict2 if
                    float(x['apr']) > apr_low and float(x['apr']) <= apr_high]
    # 年收入
    output_dict2 = [x for x in output_dict2 if
                    int(x['loan_detail']['company_income'])*(100-float(x['credit_record']['dti']))/100 > income]
    # 沒有明確或有非單一貸款目的
    output_dict2 = [x for x in output_dict2 if (
        len([word for word in keywords if word in x['description']]) == 1)]

    output_dict = output_dict + output_dict2
    output_dict = [x for x in output_dict if not(x['serial'] in backed)]
    if(len(output_dict) < 1):
        return
    assignData = {}
    for od in output_dict:
        if(monthInvest['month_remain'] >= monthInvest['order_amount']):
            assignData[od['serial']] = monthInvest['order_amount']
            monthInvest['month_remain'] -= monthInvest['order_amount']
    payload = json.dumps({
        "assignData": assignData
    })

    # 發送指定案子需求
    assignSomeResult = session_requests.post(
        "", data=payload)
    tree = html.fromstring(assignSomeResult.text)
    # 取得csrf-token
    csrf_token = list(
        set(tree.xpath("//meta[@name='csrf-token']/@content")))[0]
    # 取得 xsrf-token
    xsrf_token = session_requests.cookies.get_dict()['XSRF-TOKEN']
    # 取得 laravel_session
    laravel_session = session_requests.cookies.get_dict()['laravel_session']
    cookie = "XSRF-TOKEN="
    cookie += xsrf_token
    cookie += ";laravel_session="
    cookie += laravel_session
    headers = {
        'X-CSRF-TOKEN': csrf_token,
        'Content-Type': 'application/json',
        'Cookie': cookie
    }
    assignSomeResult = session_requests.post(
        "", data=payload, headers=headers)
    placeOrderResult = session_requests.get(
        "")
    tree = html.fromstring(placeOrderResult.text)
    # ---取得帳戶金額跟訂單金額，可判斷能不能直接扣款-------
    account_money = tree.xpath("//lnb-order")[0].attrib[':virtual-balance']
    order_money = tree.xpath("//lnb-order")[0].attrib[':order-amount']
    canPayFull = account_money >= order_money
    if(canPayFull == False):
        return
    # --------------------------------------------------
    loans_list = json.loads(tree.xpath("//lnb-order")[0].attrib[':loans'])
    memberSerial = list(
        set(tree.xpath("//div[@id='ROOT']/@data-member-serial")))[0]
    time = datetime.now(timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')
    value = {
        "update_at": time,
        "memberSerial": memberSerial,
        "contractAccepted": True
    }

    # 取得 xsrf-token
    xsrf_token = session_requests.cookies.get_dict()['XSRF-TOKEN']
    # 取得 laravel_session
    laravel_session = session_requests.cookies.get_dict()['laravel_session']
    cookie = "XSRF-TOKEN="
    cookie += xsrf_token
    cookie += ";laravel_session="
    cookie += laravel_session
    for l in loans_list:
        cookie += ";{}=".format(l['serial'])
        cookie += str(value)
    cookie += ";isNPRChecked=True"

    headers = {
        'X-CSRF-TOKEN': csrf_token,
        'Content-Type': 'application/json',
        'Cookie': cookie
    }

    loans = []
    for l in loans_list:
        ob = {'serial': l['serial'], 'timestamp': int(
            datetime.now(timezone('Asia/Taipei')).timestamp())}
        loans.append(ob)

    payload = json.dumps({
        "alliance_code": "",
        "arrive_at": datetime.now(timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S'),
        "deposit": False,
        "discount": "",
        "loans": loans,
        "mgm_serial": "",
        "password": password,
        "promo_code": "",
        "today": datetime.now(timezone('Asia/Taipei')).strftime('%Y-%m-%d')
    })

    # 結帳
    # payment_result=session_requests.post("",data=payload, headers=headers)
    # UpdateMonthInvest(output_dict)


def UpdateMonthInvest(output_dict):
    global CanRun, email, password, apr_low, apr_high, income, C_STU_NPR, monthInvest, keywords, today
    try:
        connection = mysql.connector.connect(host='localhost',
                                             database='lnbcrawler',
                                             user='root',
                                             password='root')
        sql = "update month_invest set month_remain={}".format(
            monthInvest['month_remain'])
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute(sql)
            connection.commit()
            for od in output_dict:
                sql = "insert into back_serial_log (back_item, back_amount, back_time) values('{}',{},'{}')".format(
                    od['serial'], monthInvest['order_amount'], datetime.now(timezone('Asia/Taipei')).strftime('%Y-%m-%d-%H:%M:%S'))
                cursor.execute(sql)
                connection.commit()
    except Error as e:
        print(e)
    finally:
        if (connection.is_connected()):
            cursor.close()
            connection.close()
            print("Month_invest update")


GetInfo()
Crawler()