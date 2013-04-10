# -*- coding: utf-8 -*-


import sys, getopt
import psycopg2

path = ""
init_relational_data = True
database = ""
user = 'openerp'
password = None
opts, args = getopt.getopt(sys.argv[1:], "hnd:i:u:p:", ["help", "--no-init","database=", "ifile=","user=","password"])

for opt, arg in opts:
    if opt in ('-h','--help'):
        sys.exit('Usage:\n -h: display this help message\n -i --ifile <inputcsvfile>\n -d --database <database>\n -u --user <username>\n -p --password <password>\n -n --no-init: avoid init of relational data (m20 and m2m)')
    elif opt in ('-i','--ifile'):
        path = arg
    elif opt in ('-d', '--database'):
        database = arg
    elif opt in ('-u', '--user'):
        user = arg
    elif opt in ('-p', '--password'):
        password = arg
    elif opt in ('-n','--no-init'):
        init_relational_data = False
    else:
        exit("Error : Unsupported argument")

if path == "":
    sys.exit("Error : missing input file")
if database == "":
    sys.exit("Error: missing database info")


#main script
def import_data(cr, con):
    activities = []
    activities_to_create = []
    activities_dict = {}
    partners = []
    
    fichier = open(path, "r")
    #We ignore first line, which is header of csv, not data
    fichier.readline()
    
    if init_relational_data:
        cr.execute('select name from openstc_partner_activity;')
        activities = [item[0] for item in cr.fetchall()]
        for line in fichier:
            activity = line.split(',')[2]
            if activity not in activities and activity not in activities_to_create:
                activities_to_create.append(activity)
        #print("activities:" + str(activities_to_create))
        fichier.close()
        for data in activities_to_create:
            cr.execute('insert into openstc_partner_activity(name) values (%s)', (data,))
        con.commit()
    
    #initialize m20 type_id
    cr.execute("select id from openstc_partner_type where name = 'Fournitures STC' limit 1;")
    type_id = cr.fetchone()
    if type_id:
        type_id = type_id[0]
    if not type_id:
        cr.execute("insert into openstc_partner_type(name, code) values('Fournitures STC', 'FOURNISSEUR');")
        cr.execute("select id from openstc_partner_type where name = 'Fournitures STC' limit 1;")
        type_id = cr.fetchone()
        if type_id:
            type_id = type_id[0]
    
        
    #initialize m2o data and suppliers already created 
    cr.execute('select id, name from openstc_partner_activity;')
    activities = cr.fetchall()
    for item in activities:
        activities_dict[item[1]] = item[0]
    
    cr.execute('select name from res_partner where supplier=True;')
    partners = [item[0] for item in cr.fetchall()]
    
    #import data of suppliers
    fichier = open(path, "r")
    #We ignore first line, which is header of csv, not data
    fichier.readline()
    for line in fichier:
        data = line.split(',')
        if not data[1] in partners:
            #we create new partner
            cr.execute('insert into res_partner(active, supplier, name, code_tiers_ciril, type_id) values(True, True, %s, %s, %s)', (data[1], data[0], int(type_id)))
            cr.execute('insert into res_partner_address(active, name,street,street2,zip,city, partner_id) values(True, %s,%s,%s,%s,%s, (select id from res_partner where name = %s limit 1) )', (data[7], data[3], data[4],data[6],data[5], data[1]))
            if data[2] and data[2] <> "":
                cr.execute('insert into openstc_partner_activity_rel values((select id from res_partner where name = %s limit 1), %s)', (data[1], activities_dict[data[2]]))
    con.commit()
    fichier.close()

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