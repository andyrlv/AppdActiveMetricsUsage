___author___ = "Andrey Orlov // andrey.orlov@appdynamics.com"

import requests
import configparser
import xmltodict, json

config = configparser.ConfigParser()
config.read('config.ini')

class GeneralAppdConnector(object):

    def __init__(self):
        self.hostport = config['APPD']['hostport']
        self.user = config['APPD']['user']
        self.account = config['APPD']['account']
        self.password = config['APPD']['password']
        self.headers = { "Content-Type": "application/json" }


    def getConnectionData(self):
        path = 'auth?action=login'
        print("Getting: {}".format(path))
        r = requests.get("{}/{}".format(self.hostport,path),headers=self.headers, auth=(self.user + '@' + self.account, self.password))
        self.session = r.cookies.get('JSESSIONID')
        self.csrf = r.cookies.get('X-CSRF-TOKEN')
        self.cookies = r.cookies
        self.headers['X-CSRF-TOKEN'] = self.csrf
        return
 
    def getData(self, path):
        r = requests.get("{}/{}".format(self.hostport,path),headers=self.headers, auth=(self.user + '@' + self.account, self.password), cookies=self.cookies)
        return r 

class Metrics(object):
    def __init__(self):
        self.connector = GeneralAppdConnector()

    def getMetricsFromDashboard(self, dashboard):
        if 'name' not in dashboard or dashboard['widgetTemplates'] is None:
            return []

        metrics = []
        for widget in dashboard['widgetTemplates']:
            if widget['dataSeriesTemplates'] is not None:
                for series in widget['dataSeriesTemplates']:
                    metrics.append(series)
        return metrics
    
    def writeDataToFile(self, fileName, jsonData) :
        with open(fileName, 'w') as file:
            for el in jsonData:
                file.write(json.dumps(el))
                file.write('\n')

    def getData(self):
        # set connection to Controller
        self.connector.getConnectionData()
        # get all dashboards from Controller
        dashboards = self.connector.getData('restui/dashboards/getAllDashboardsByType/false').json()
        #collect metrics from dashboards
        metrics = []
        for dashboard in dashboards:
            metrics += self.getMetricsFromDashboard(self.connector.getData('CustomDashboardImportExportServlet?dashboardId={}'.format(dashboard['id'])).json())

        #debug
        self.writeDataToFile('metrics.txt', metrics)


        # GET ALL METRICS FROM HEALTHRULES
        # get list of applications
        apps = self.connector.getData('rest/applications')
        apps = json.loads(json.dumps(xmltodict.parse(apps.text)))
        apps = apps['applications']['application']
        healthrulemetrics = []
        i = 0
        for app in apps:
            print('Processing {} from {}'.format(i, len(apps)))
            i += 1
            if i == 5:
                break

            # get list of application's healthrules
            healthrules = self.connector.getData('alerting/rest/v1/applications/{}/health-rules'.format(app['id'])).json()
            for healthrule in healthrules:
                hr = self.connector.getData('alerting/rest/v1/applications/{}/health-rules/{}'.format(app['id'], healthrule['id'])).json()
                healthrulemetrics.append(hr) 

        self.writeDataToFile('healthrulesmetrics.txt', healthrulemetrics)
        return metrics

if __name__ == "__main__":
    m = Metrics()
    metrics = m.getData()
    print(metrics)
