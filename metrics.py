___author___ = "Andrey Orlov // andrey.orlov@appdynamics.com"

import requests
import configparser
import json

DATA = 'data/'
DASHBOARDSMETRICFILE = 'dashboardmetrics.csv'
HEALTHRULESMETRICSFILE = 'healthrulesmetrics.csv'
DEBUG = False

config = configparser.ConfigParser()
config.read('config.ini')

class GeneralAppdConnector(object):

    def __init__(self):
        self.hostport = config['APPD']['hostport']
        self.user = config['APPD']['user']
        self.account = config['APPD']['account']
        self.password = config['APPD']['password']
        self.headers = { "Content-Type": "application/json" }
        self.analytics = config['APPD']['analytics']


    def getConnectionData(self):
        print('Getting Auth information...')
        path = 'auth?action=login'
        r = requests.get("{}/{}".format(self.hostport,path),headers=self.headers, auth=(self.user + '@' + self.account, self.password))
        self.session = r.cookies.get('JSESSIONID')
        self.csrf = r.cookies.get('X-CSRF-TOKEN')
        self.cookies = r.cookies
        self.headers['X-CSRF-TOKEN'] = self.csrf
        print ('Login successful!')
        return
 
    def getData(self, path):
        r = requests.get("{}/{}".format(self.hostport,path),headers=self.headers, auth=(self.user + '@' + self.account, self.password), cookies=self.cookies)
        return r 

class Metrics(object):
    def __init__(self):
        self.connector = GeneralAppdConnector()

    def getDataFromDashboards(self):
        # GET ALL METRICS FROM DASHBOARDS
        dashboards = self.connector.getData('restui/dashboards/getAllDashboardsByType/false').json()
        #collect metrics from dashboards
        metrics = {}
        index = 0
        for dashboard in dashboards:
            index += 1
            if DEBUG and index == 5:
                break
            metrics.update(self.getMetricsFromDashboard(self.connector.getData('CustomDashboardImportExportServlet?dashboardId={}'.format(dashboard['id'])).json()))
        
        return metrics

    def getMetricsFromDashboard(self, dashboard):
        # Check valid dashboard or not
        if 'name' not in dashboard or dashboard['widgetTemplates'] is None:
            print('Invalid dashboard!')
            return {}
        print ('Getting data from dashboard -> {}'.format(dashboard['name']))
        
        print('Collecting metrics...')
        metrics = []
        cleanmetrics = {}
        for widget in dashboard['widgetTemplates']:
            if widget['dataSeriesTemplates'] is not None:
                for series in widget['dataSeriesTemplates']:
                    metrictmpdata = {}
                    metrictmpdata['type'] = 'dashboard'
                    metrictmpdata['name'] = dashboard['name']
                    metrics.append(series)
                    metric = series
                    # clean metrics - get only what we need
                    metrictmpdata['metricType'] = metric['metricType']
                    metrictmpdata['application'] = metric['metricMatchCriteriaTemplate']['applicationName']

                    # Metrics with absolut path
                    if metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['metricExpressionType'] == 'Absolute' :
                        metrictmpdata['metricPath'] = metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['metricPath']
                        cleanmetrics[self.getHashFromMetric(metrictmpdata)] = metrictmpdata
                    # Metrics with several expressions
                    elif metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['metricExpressionType'] == 'Boolean' :
                        i = 1
                        while 'expression' + str(i) in metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']:
                            tmpdatax = dict(metrictmpdata)
                            if 'relativeMetricPath' in metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['expression' + str(i)]:
                                tmpdatax['metricPath'] = metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['expression' + str(i)]['relativeMetricPath']
                                cleanmetrics[self.getHashFromMetric(tmpdatax)] = tmpdatax
                            i += 1
                    # Metrics with only one expression
                    elif metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['metricExpressionType'] == 'Logical' :
                        metrictmpdata['metricPath'] = metric['metricMatchCriteriaTemplate']['metricExpressionTemplate']['relativeMetricPath']
                        cleanmetrics[self.getHashFromMetric(metrictmpdata)] = metrictmpdata
        print ('Metrics are collected!')
        print ('-------------')
        return cleanmetrics

    def getHashFromMetric(self, metric):
        return hash(json.dumps(metric, sort_keys=True))

    def getDataFromHealthrules(self):
        # GET ALL METRICS FROM HEALTHRULES
        # get list of applications
        apps = self.connector.getData('rest/applications?output=JSON').json()
        # Don't touch this hard code, if you want analytics health rules...
        apps.append({'id': self.connector.analytics, 'name': 'Analytics'})

        healthrulemetrics = {}
        index = 0
        for app in apps:
            print('Processing {} ({}) from {}'.format(index + 1, app['name'], len(apps)))
            index += 1
            if DEBUG and index == 5:
                break

            # get list of application's healthrules
            healthrules = self.connector.getData('alerting/rest/v1/applications/{}/health-rules'.format(app['id'])).json()
            for healthrule in healthrules:
                hr = self.connector.getData('alerting/rest/v1/applications/{}/health-rules/{}'.format(app['id'], healthrule['id'])).json()
                # Preparing structure
                tmphr = {}
                tmphr['type'] = 'healthrule'
                tmphr['application'] = app['name']
                tmphr['name'] = hr['name']
                tmphr['metricType'] = ''
                if 'affects' in hr:
                    tmphr['metricType'] = hr['affects']['affectedEntityType']
                
                tmphr['metricPath'] = ' '
                
                isCriteria = False
                for i in range(2):
                    criteria = 'warningCriteria' if i == 0 else 'criticalCriteria'
                    if criteria in hr['evalCriterias'] :
                        isCriteria = True
                        for condition in hr['evalCriterias'][criteria]['conditions']:
                            if condition['evalDetail']['evalDetailType'] == 'SINGLE_METRIC':
                                tmphrx = dict(tmphr)
                                tmphrx['metricPath'] = condition['evalDetail']['metricPath']
                                healthrulemetrics[self.getHashFromMetric(tmphrx)] = tmphrx
                            elif condition['evalDetail']['evalDetailType'] == 'METRIC_EXPRESSION':
                                for metricexpvariable in condition['evalDetail']['metricExpressionVariables']:
                                    tmphrx = dict(tmphr)
                                    tmphrx['metricPath'] = metricexpvariable['metricPath']
                                    healthrulemetrics[self.getHashFromMetric(tmphrx)] = tmphrx
                            else:
                                raise()
                if not isCriteria:
                    healthrulemetrics[self.getHashFromMetric(tmphr)] = tmphr
        return healthrulemetrics
    
    def writeDataToFile(self, fileName, jsonData) :
        with open(fileName, 'w') as file:
            file.write('Type,Application,Name,MetricType,MetricPath')
            file.write('\n')
            for el in jsonData:
                file.write('{},{},{},{},{}'.format(
                    jsonData[el]['type'],
                    jsonData[el]['application'],
                    jsonData[el]['name'],
                    jsonData[el]['metricType'],
                    jsonData[el]['metricPath']))
                file.write('\n')

    def getData(self):
        # set connection to Controller
        self.connector.getConnectionData()

        # collect dashboard metrics
        dashboardsmetrics = self.getDataFromDashboards()
        self.writeDataToFile(DATA + DASHBOARDSMETRICFILE, dashboardsmetrics)
        
        # collect health rules metrics
        healthrulemetrics = self.getDataFromHealthrules()
        self.writeDataToFile(DATA + HEALTHRULESMETRICSFILE, healthrulemetrics)
        return healthrulemetrics


if __name__ == "__main__":
    m = Metrics()
    metrics = m.getData()
    #print(metrics)

