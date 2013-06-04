# -*- coding: utf-8 -*-
#author: PLANCHER Bruno

import sys, getopt
import psycopg2
from datetime import datetime
path = ""
init_relational_data = True
database = ""
user = 'openerp'
password = None
opts, args = getopt.getopt(sys.argv[1:], "hd:i:u:p:", ["help","database=", "ifile=","user=","password"])

for opt, arg in opts:
    if opt in ('-h','--help'):
        sys.exit('Usage:\n -h: display this help message\n -i --ifile <inputcsvfile>\n -d --database <database>\n -u --user <username>\n -p --password <password>\n')
    elif opt in ('-i','--ifile'):
        path = arg
    elif opt in ('-d', '--database'):
        database = arg
    elif opt in ('-u', '--user'):
        user = arg
    elif opt in ('-p', '--password'):
        password = arg
    else:
        exit("Error : Unsupported argument")

if path == "":
    sys.exit("Error : missing input file")
if database == "":
    sys.exit("Error: missing database info")

#main script
def import_data(cr, con):
    accounts = []
    accounts_to_create = []
    accounts_dict = {}
    analytics = []
    analytics_to_create = []
    analytics_dict = {}
    services_dict = {}
    services_line_nb = {}

    fichier = open(path, "r")
    for line in fichier:
        line_split = line.split(';')
        #check if all account_account needed exist, exit with error status otherwise
        account = line_split[6]
        cr.execute('select id,code from account_account where code like \'%s\';' % str(account + '%'))
        res = cr.fetchone()
        if res:
            accounts.append(res[1])
            accounts_dict[account] = res[0]
        elif account not in accounts_to_create:
            accounts_to_create.append(account)
#    accounts = [item[0] for item in cr.fetchall()]
    fichier.close()
    if accounts_to_create:
        sys.exit('Error, you need to create thus accounts before importing this csv budget file %s' % accounts_to_create)
        
    #init account_analytic_account and create missing records
    fichier = open(path, "r")
    cr.execute('select name from account_analytic_account;')
    analytics = [item[0] for item in cr.fetchall()]
    for line in fichier:
        split_line = line.split(';')
        analytic = split_line[7]
        code_serv = split_line[2]
        service = split_line[3]
        services_line_nb.setdefault(service,[])
        services_line_nb[service].append(split_line)
        if analytic not in analytics and analytic not in analytics_to_create:
            analytics_to_create.append([analytic,code_serv])
    fichier.close()
    for item in analytics_to_create:
        cr.execute('insert into account_analytic_account(state, name) values(\'open\',%s)', (item[0],))
    #create services that are not in bd, update others with ciril infos
    for service in services_line_nb.values():
        cr.execute('select id,code,name from openstc_service where unaccent(name) ilike %s;', (service[0][3],))
        res = cr.fetchone()
        if not res:
            cr.execute('insert into openstc_service(name, code, code_serv_ciril, code_gest_ciril, code_function_ciril) values(%s,%s,%s,%s,%s);', (service[0][3],
                                                                                                                                              service[0][2],
                                                                                                                                              service[0][2],
                                                                                                                                              service[0][0],
                                                                                                                                              service[0][1]))
        else:
            cr.execute('update openstc_service set code=%s, code_serv_ciril=%s, code_gest_ciril=%s, code_function_ciril=%s where id=%s', (service[0][2],
                                                                                                                                        service[0][2],
                                                                                                                                        service[0][0],
                                                                                                                                        service[0][1],
                                                                                                                                        res[0]))
    
    #import data of budgets
    now = datetime.now()
    cr.execute('select id from account_budget_post;')
    post_id = cr.fetchone()
    if not post_id:
        cr.execute('select nextval(\'account_budget_post_id_seq\');')
        post_id = cr.fetchone()
        print post_id #DEBUG
        cr.execute('insert into account_budget_post(id,name,code,company_id) values(%s,\'Factice\',\'factice\',1);', (post_id,))
        cr.execute('insert into account_budget_rel(account_id,budget_id) values((select id from account_account limit 1),%s)',(post_id,))
    else:
        post_id = post_id[0]
        
    cr.execute('select id, name from account_analytic_account;')
    for item in cr.fetchall():
        analytics_dict[item[1]] = item[0]
    
    current_service = ''
    for service, data in services_line_nb.items():
        current_service = service
        date_from = '%s-01-01' % now.year
        date_to = '%s-12-31' % now.year
        #we create one crossovered budget for all budget lines of same service
        cr.execute('insert into crossovered_budget(state, company_id, name,code,date_from,date_to,service_id) values(\'draft\',1,%s,%s,%s,%s,(select id from openstc_service where code=%s limit 1));', (current_service + ' ' + str(now.year),
                                                                                                        data[0][2] + ' ' + str(now.year), 
                                                                                                        date_from, 
                                                                                                        date_to,
                                                                                                        data[0][2]))
        cr.execute('select id from crossovered_budget order by id desc limit 1')
        budget_id = cr.fetchone()[0]
        #we create one record per budget line in csv, item contains each line split by csv separator
        
        for item in data:
            planned_amount = float(item[8].replace(' ','').replace(',','.'))
            if planned_amount > 0.0:
                cr.execute('insert into crossovered_budget_lines(crossovered_budget_id,analytic_account_id, general_budget_id,openstc_general_account,openstc_code_antenne,date_from,date_to,planned_amount) values(%s,%s,%s,%s,%s,%s,%s,%s)', (budget_id,
                                                                                                                                                                                                                   analytics_dict[item[7]],
                                                                                                                                                                                                                   post_id,
                                                                                                                                                                                                                   accounts_dict[item[6]],
                                                                                                                                                                                                                   item[4] or '0',
                                                                                                                                                                                                                   date_from,
                                                                                                                                                                                                                   date_to,
                                                                                                                                                                                                                   planned_amount))
    con.commit()
    #fichier.close()

if __name__ == '__main__':
    con = psycopg2.connect(database=database, user=user, password=password, host="localhost", port="5432")
    cr = con.cursor()
    try:
        import_data(cr, con)
        print("Data successfully imported in OpenERP")
    except psycopg2.DatabaseError, e:
        if con:
            con.rollback()
        sys.exit('Error: %s' %e)