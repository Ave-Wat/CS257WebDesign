'''
    api.py for MIAC analysis webapp
    Avery Watts and Ben Aoki-Sherwood
    15 November 2020

    adapted from Jeff Ondich's api.py for CS257 Carleton College, Fall 2020
    API to support the MIAC analysis webapp.
'''
import sys
import flask
import json
import config
import psycopg2

########### Initializing Flask ###########
# We're using a Flask "Blueprint" to enable us to put the website pages
# in the main Flask application (in books_webapp.py) and the API over
# here. Since the website and the API are conceptually separate, I like
# to keep them in separate files. This gets more worthwhile as the
# application grows.
api = flask.Blueprint('api', __name__)


########### Utility functions ###########
def get_connection():
    ''' Returns a connection to the database described in the
        config module. May raise an exception as described in the
        documentation for psycopg2.connect. '''
    return psycopg2.connect(database=config.database,
                            user=config.user,
                            password=config.password)

########### The API endpoints ###########

@api.route('/search')
def get_search_results():
    ''' returns a list of dictionaries of race results by athlete, team, or year
    '''
    field = flask.request.args.get('field')
    keyword = flask.request.args.get('keyword')
    results = []
    if field == 'athletes':
        results = search_athletes(keyword)
    elif field == 'teams':
        results = search_teams(keyword)
    elif field == 'year':
        results = search_years(keyword)
    return json.dumps(results)

def search_athletes(keyword):
    #{athlete_name: {team:teamname, performances:{year:[place,time],...}}}
    query = '''SELECT athletes.name, teams.name, year, place, time
               FROM teams, athletes, meets, individual_performances
               WHERE individual_performances.team_id = teams.id
               AND meet_id = meets.id
               AND individual_performances.ath_id = athletes.id
               AND LOWER(athletes.name) LIKE %s '''
    query_argument = '%' + keyword.lower() + '%'
    cursor = get_cursor(query, query_argument)
    athletes_dict = {}
    for row in cursor:
        time = convert_time_to_minutes(row[4])
        place = parse_DNF(row[3])
        if row[0] in athletes_dict:
            athletes_dict[row[0]]['performances'][row[2]] = [place, time]
        else:
            athletes_dict[row[0]] = {'team':row[1], 'performances':{row[2]:[place,time]}}
    cursor.close()

    return athletes_dict
    '''
    query = 'SELECT athletes.name, place, time, teams.name, year
                FROM athletes, teams, individual_performances, meets
                WHERE ath_id = athletes.id
                AND team_id=teams.id
                AND meet_id=meets.id
                AND LOWER(athletes.name) LIKE %s'
    query_argument = '%' + keyword.lower() + '%'
    cursor = get_cursor(query, (query_argument,))
    athletes_list = []
    for row in cursor:
        place = parse_DNF(row[1])
        athlete = {'name': row[0], 'team': row[3], 'place': place, 'time': convert_time_to_minutes(row[2]), 'year': row[4]}
        athletes_list.append(athlete)
    cursor.close()
    return athletes_list'''

def search_teams(keyword):
    #{team:{'location':location, 'performances':{year:[place, points]},...}}
    query = ''' SELECT teams.name, teams.location, year, place, points
                FROM teams, meets, team_performances
                WHERE team_id = teams.id
                AND meet_id = meets.id
                AND LOWER(teams.name) LIKE %s '''
    query_argument = '%' + keyword.lower() + '%'
    cursor = get_cursor(query, query_argument)
    teams_dict = {}
    for row in cursor:
        if row[0] in teams_dict:
            teams_dict[row[0]]['performances'][row[2]] = [row[3], row[4]]
        else:
            teams_dict[row[0]] = {'location':row[1], 'performances':{row[2]:[row[3],row[4]]}}
    cursor.close()

    return teams_dict

    # query = ''' SELECT teams.name, place, points, year, teams.location
    #             FROM teams, meets, team_performances
    #             WHERE team_id=teams.id
    #             AND meet_id=meets.id
    #             AND LOWER(teams.name) LIKE %s '''
    # query_argument = '%' + keyword.lower() + '%'
    # team_performances_list = []
    # cursor = get_cursor(query, (query_argument,))
    # for row in cursor:
    #     team_performance = {'name': row[0], 'location': row[4], 'place': row[1], 'points': row[2], 'year': row[3]}
    #     team_performances_list.append(team_performance)
    # cursor.close()
    # return team_performances_list

def search_years(keyword):
    teams_query = ''' SELECT teams.name, place, points, meets.location
                      FROM teams, meets, team_performances
                      WHERE meet_id = meets.id
                      AND team_id = teams.id
                      AND year = %s ORDER BY place '''
    query_argument = keyword
    individuals_query = '''SELECT athletes.name, place, time, teams.name
                           FROM athletes, individual_performances, teams, meets
                           WHERE meet_id = meets.id
                           AND team_id = teams.id
                           AND ath_id = athletes.id
                           AND year = %s ORDER BY place '''
    teams_cursor, individuals_cursor = get_cursor(teams_query, (query_argument,)), get_cursor(individuals_query, (query_argument,))
    teams_list, individuals_list = [], []
    for row in teams_cursor:
        team = {'name': row[0], 'place': row[1], 'points': row[2], 'location': row[3]}
        teams_list.append(team)
    for row in individuals_cursor:
        place = parse_DNF(row[1])
        individual = {'name': row[0], 'team': row[3], 'place': place, 'time': convert_time_to_minutes(row[2])}
        individuals_list.append(individual)
    teams_cursor.close()
    individuals_cursor.close()
    return [teams_list, individuals_list]

@api.route('/teams_performances')
def get_teams_performances():
    '''returns a dictionary as such: {team1: [list of places from 2009 to 2019], team2: [(same)], etc for all teams in team_codes}'''
    '''input: ?teams={team_codes}
    	*team_codes is a list of numbers 0-10 corresponding to a particular MIAC team alphabetically'''
    team_codes = flask.request.args.get('teams').split(',')
    teams_performances = {}
    for team_id in team_codes:
        team_name = get_team_name(team_id)
        teams_performances[team_name] = get_single_team_performances(team_name)

    return json.dumps(teams_performances)

def get_single_team_performances(team_name):
    query = "SELECT teams.name, place, year FROM teams, meets, team_performances WHERE team_performances.team_id = teams.id AND teams.name = '" + team_name + "' AND meets.id=meet_id ORDER BY year"
    #SELECT teams.name, place, year FROM teams, meets, team_performances WHERE team_performances.team_id = teams.id AND teams.name='Carleton' AND meets.id=meet_id ORDER BY year;
    cursor = get_cursor(query, '')
    team_performances = []
    for row in cursor:
        team_performances.append(row[1])
    cursor.close()
    return team_performances

@api.route('/team_depth')
def get_teams_depth():
    '''returns a JSON dict of dictionaries as such: {"2019":{team1:[list of 7 times], team2:[list of 7 times], etc for each selected team}, "2018":{(as before)}, etc for each selected year}'''
    '''input: ?teams={team_codes}&years={years}
        team_codes is a list of numbers 0-13 corresponding to a particular MIAC team alphabetically and
        years is a list of the years to be included in the query'''

    teams = flask.request.args.get('teams').split(",")
    years = flask.request.args.get('years').split(",")
    teams_depth_dict = {}
    for year in years:
        teams_dicts = {}
        for team_id in teams:
            team_name = get_team_name(team_id)
            teams_dicts[team_name] = get_team_depth_by_year(team_name, year)
        teams_depth_dict[year] = teams_dicts
    return json.dumps(teams_depth_dict)

def get_team_depth_by_year(team_name, year):
    '''returns a list of up to 7 times'''
    query = "SELECT time FROM teams, athletes, meets, individual_performances, athlete_team_links WHERE individual_performances.team_id = teams.id AND meet_id = meets.id AND teams.name = '" + team_name + "' AND year = '" + year + "' AND teams.id = athlete_team_links.team_id AND athlete_team_links.ath_id = athletes.id AND individual_performances.ath_id = athletes.id LIMIT 7"
    cursor = get_cursor(query, '')
    performances_list = []
    for row in cursor:
        performances_list.append(row[0])
    cursor.close()
    return performances_list

@api.route('/athlete_development')
def athlete_development():
    ''' returns a JSON dictionary of lists with teams as keys corresponding to a list of average change in athlete
    	performance (measured by place or time depending on the sort_by parameter) ordered by year for the team
        input: ?calculate_by=[place, time]&teams={team_codes}, team_codes as before'''
    team_codes = flask.request.args.get('teams').split(",")
    calculate_by = flask.request.args.get('calculate_by')

    teams_athlete_performances = {}
    for team_id in team_codes:
        team_name = get_team_name(team_id)
        teams_athlete_performances[team_name] = get_athlete_performances_by_team(team_name, calculate_by)

    return json.dumps(teams_athlete_performances)

def get_athlete_performances_by_team(team_name, calculate_by):
    '''returns a dict with athlete names as keys and a list of lists, so that: {athlete_name: [[time, year], etc for multiple years], etc for multiple athletes}'''
    query = "SELECT athletes.name," + calculate_by + ", year FROM teams, athletes, meets, individual_performances, athlete_team_links WHERE individual_performances.team_id = teams.id AND meet_id = meets.id AND teams.name = '" + team_name + "' AND teams.id = athlete_team_links.team_id AND athlete_team_links.ath_id = athletes.id AND individual_performances.ath_id = athletes.id"
    #"SELECT athletes.name, time, teams.name FROM teams, athletes, meets, individual_performances, athlete_team_links WHERE individual_performances.team_id = teams.id AND meet_id = meets.id AND teams.name = 'Carleton' AND teams.id = athlete_team_links.team_id AND athlete_team_links.ath_id = athletes.id AND individual_performances.ath_id = athletes.id;"

    cursor = get_cursor(query, '')
    performances_dict = {}

    for row in cursor:
        if row[0] in performances_dict:
            performances_dict[row[0]].insert(0, [row[1], row[2]])
        else:
            performances_dict[row[0]] = [[row[1], row[2]]]
    cursor.close()

    return performances_dict

'''methods below are used for multiple methods'''
def get_cursor(query, query_arguments):
    try:
        connection = get_connection()
        cursor = connection.cursor()
        if query_arguments != '':
            cursor.execute(query, (query_arguments,))
        else:
            cursor.execute(query)
    except Exception as e:
        print(e, file=sys.stderr)
    return cursor

def convert_time_to_minutes(time):
    if time != None:
        minutes = str(int(time // 60))
        seconds = int(time % 60)
        if seconds < 10:
            seconds = '0' + str(seconds)
        else:
            seconds = str(seconds)
        timeString = minutes + ':' + seconds
        return timeString
    else:
        return "---"

def get_team_name(team_id):
    team_id = int(team_id)
    team_list = ['Augsburg', 'Bethel', 'Carleton', 'Concordia-Moorhead', 'Gustavus Adolphus', 'Hamline', 'Macalester', "Saint John''s", "Saint Mary''s", 'St. Olaf', 'St. Thomas']
    team_name = team_list[team_id]
    return team_name

def parse_DNF(place):
    '''Handles the case when an athlete entered the race but Did Not Finish,
    indicating DNF if this is the case'''
    if place == None:
        return 'DNF'
    else:
        return place
