import psycopg2 as sql
import time
import json
import uuid
from core import utils, config
from core.models import TagLabel, ClassLabel, Timeseries, Classification, Tag
import time
import logging

logger = logging.getLogger(__name__)

NO_MATCH_CLASS = {
    'id': -2,
    'name': 'NO MATCH FOR AUTOCLASS',
    'international_id': -2
}

# This class is referenced _exactly_ by name in "hotkeys.js"
# Changing the name here requires it to be changed there as well!
NO_ANNOTATION_CLASS = {
    'id': -1,
    'name': 'No annotation',
    'international_id': -1
}


# NOTE: Throughout this application, PIDs and bins are stored and transferred WITHOUT the timeseries url prepended

# Filtering using django objects is fast, but then iterating through them is slow
# so instead we'll use lower level SQL to sort the results ahead of time (seems to be about 70x faster!)

# Param 1: an array of strings, representing bins
# Param 2: a dictionary, indexed by PID, with values that are dictionaries containing keys 'width' and 'height'
#     for all PIDs in the given bins
# Output: a dictionary, indexed by PID, with values that are dictionaries containing all data for all classifications
#    relevant to the given bins, ready to be passed to JS or to another function that will add the auto classifier data
def getAllDataForBins(bins, targets, timeseries):
    # since timeseries_id should already be held in memory, no point in joining that table again in below query
    timeseries_id = getTimeseriesId(timeseries)

    params = [timeseries_id]

    # result column order:
    # 0   1    2    3        4     5                  6      7              8                  9              10     11        12
    # id, bin, roi, user_id, time, classification_id, level, verifications, verification_time, timeseries_id, power, username, pid
    query = ('SELECT c.*, p.power, u.username, c.bin || \'_\' || LPAD(c.roi::text, 5, \'0\') as pid '
             'FROM classify_classification c, auth_user_groups g, auth_group p, auth_user u '
             'WHERE c.user_id = g.user_id '
             'AND c.user_id = u.id '
             'AND p.id = g.group_id '
             'AND c.timeseries_id::uuid = %s '
             'AND c.bin in (')
    for bin in bins:
        query += '%s, '
        params.append(bin)
    query = query[:-2] + ');'
    # now that JS wants to order itself, we don't order here
    # query += 'ORDER BY pid, p.power DESC, c.verification_time DESC NULLS LAST, c.time DESC;'

    conn = sql.connect(database=config.db, user=config.username, password=config.password, host=config.server)
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    data = {}

    for row in rows:
        dict = {
            'id': row[0],
            'user_id': row[3],
            'time': row[4].isoformat(),
            'classification_id': row[5],
            'level': row[6],
            'verifications': row[7],
            'verification_time': row[8].isoformat() if row[8] else None,
            'timeseries_id': row[9],
            'user_power': row[10],
            'username': row[11]
        }
        if not row[12] in data:
            data[row[12]] = {
                'pid': row[12],
                # sometimes in Javascript these dictionaries are disassociated from their keys, but we still need to know their PID
                'width': targets[row[12]]['width'],
                'height': targets[row[12]]['height'],
                'classifications': [dict],
                'tags': [],
            }
        else:
            data[row[12]]['classifications'].append(dict)

    # now loop all targets given by Param 2
    for pid, dims in targets.items():
        # if we didn't already find any annotations for this pid
        if not pid in data:
            # insert some default values and height/width
            data[pid] = {
                'pid': pid,
                'width': dims['width'],
                'height': dims['height'],
                'classifications': [],
                'tags': [],
            }

    # now we query for tags, but the 'accepted' logic for them is less straightforward, so we'll leave that to JS
    # here, we simply add tags to the 'tags' array for their respective pids

    # result column order:
    # 0   1    2    3        4     5       6      7              8                  9              10        11     12        13
    # id, bin, roi, user_id, time, tag_id, level, verifications, verification_time, timeseries_id, negation, power, username, pid
    query = ('SELECT t.*, p.power, u.username, t.bin || \'_\' || LPAD(t.roi::text, 5, \'0\') as pid '
             'FROM classify_tag t, auth_user_groups g, auth_group p, auth_user u '
             'WHERE t.user_id = g.user_id '
             'AND t.user_id = u.id '
             'AND p.id = g.group_id '
             'AND t.timeseries_id::uuid = %s '
             'AND t.bin in (')
    for bin in bins:
        query += '%s, '
    query = query[:-2] + ');'

    cur.execute(query, params)
    rows = cur.fetchall()

    for row in rows:
        data[row[13]]['tags'].append({
            'id': row[0],
            'user_id': row[3],
            'time': row[4].isoformat(),
            'tag_id': row[5],
            'level': row[6],
            'verifications': row[7],
            'verification_time': row[8].isoformat() if row[8] else None,
            'timeseries_id': row[9],
            'negation': row[10],
            'user_power': row[11],
            'username': row[12],
        })

    return data


# Unfortunately, Django doesn't seem to have a good way to do many UPSERTs at once (I tried just looping objects, and it's PAINFULLY slow)
#     so we have to drop back down to SQL for this too
# Since this function is practically identical for classifications/tags (with only minor SQL differences), it handles both use cases
# This may make the function overly complex and hard to maintain, so I may change it in the future, but it works for now

# Param 1: a dictionary, indexed by PID, with integer values representing the new classification/tag id to assign that PID to
# Param 2: an integer, representing the user id of the user submitting these updates
# Param 3: a boolean, representing whether these updates are classifications (True) or tags (False)
# Param 4: a boolean, representing whether these updates are negations (True) or not (False) -- only relevant if Param 3 is False
#    if this value is True, then Param 1's dictionary values are actually arrays of integers, instead of single integers
# Output: a dictionary, with format:
#    'classifications' : {
#        PID : {...}
#    }
#    'tags' : {
#        PID : [
#            {...},
#            {...},
#        ]
#    }
# where ... represents all data for an entry that was updated or inserted
def insertUpdates(updates, user_id, is_classifications, negations, timeseries):
    # if we don't have any updates, just stop
    if not updates or len(updates) == 0:
        return {}

    return_updates = {}

    # set some values, depending on whether these are classification or tag updates
    table = 'classify_classification'
    col = 'classification_id'
    if is_classifications:
        return_updates['classifications'] = {}
    else:
        return_updates['tags'] = {}
        table = 'classify_tag'
        col = 'tag_id'

    # begin to build the query string
    # unfortunately it seems Django Model defaults aren't actually set as defaults in the database
    # so because we are doing a manual insert, we need to provide a value for every single column
    query = 'INSERT INTO ' + table + ' (bin, roi, user_id, time, ' + col + ', level, verifications, verification_time, timeseries_id'

    # the tag table also has a `negation` column that needs to be handled
    if not is_classifications:
        query = query + ', negation'

    # loop updates and build the VALUES portion of the query string
    query = query + ') VALUES '

    # now we're looking at user inputs, so we need to pass paramters to psycopg2 instead of inserting directly into the query
    params = [];

    for pid, id in updates.items():

        # parse out the bin and roi from pid
        i = pid.rfind('_')
        bin = pid[:i]
        roi = pid[i + 1:]

        if not is_classifications:
            # if these are tags or negations, each `id` is actually an array of ids
            neg = 'true' if negations else 'false'
            for trueID in id:
                query = query + '(%s, %s, %s, now(), %s, 1, 0, null, %s, ' + neg + '), '
                params.extend([bin, roi, user_id, trueID, getTimeseriesId(timeseries)])
        else:
            query = query + '(%s, %s, %s, now(), %s, 1, 0, null, %s), '
            params.extend([bin, roi, user_id, id, getTimeseriesId(timeseries)])

    # trim off the trailing space and comma
    query = query[:-2]

    # handle conflicts that require an update instead of an insert
    query = query + ' ON CONFLICT (bin, roi, user_id, ' + col + ''
    if not is_classifications:
        query = query + ', negation'
    query = query + ') DO UPDATE SET (verifications, verification_time) = (' + table + '.verifications + 1, now()) RETURNING *;'

    conn = sql.connect(database=config.db, user=config.username, password=config.password, host=config.server)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    rows = cur.fetchall()

    # loop returned (affected) rows and build dictionaries to be passed to JS
    for row in rows:

        # I'm not sure if there's a better way to access columns
        # This is risky because if the schema changes, the indices are all thrown off
        pid = row[1] + '_' + utils.formatROI(row[2])
        dict = {
            'id': row[0],
            'user_id': row[3],
            'time': row[4].isoformat(),
            'level': row[6],
            'verifications': row[7],
            'verification_time': row[8],
            'user_power': utils.getUserPower(row[3]),
            'username': utils.getUserName(row[3]),
            'timeseries_id': row[9],
        }

        if dict['verification_time']:
            dict['verification_time'] = dict['verification_time'].isoformat()

        if is_classifications:
            dict['classification_id'] = row[5]
            return_updates['classifications'][pid] = dict
        else:
            dict['tag_id'] = row[5]
            dict['negation'] = row[10]
            if not pid in return_updates['tags']:
                return_updates['tags'][pid] = []
            return_updates['tags'][pid].append(dict)

    conn.close()
    return return_updates


def filterBins(bins, views, sortby):
    if len(views) == 0 or len(bins) == 0:
        return []

    t1 = time.time()

    # there's definitely a better way to do this,
    # but I'm gonna do it recursively and hope it's not too slow

    classID = views[0][0]
    tagIDs = views[0][1]

    params = []

    query = ('WITH '
             'CA AS ( '
             'SELECT DISTINCT ON (c.bin, c.roi) c.*, p.power '
             'FROM classify_classification c, auth_user_groups g, auth_group p '
             'WHERE c.user_id = g.user_id '
             'AND p.id = g.group_id '
             'AND c.bin in (')

    for bin in bins:
        query += '%s, '
        params.append(bin)

    query = query[:-2]

    query = query + (') '
                     'ORDER BY c.bin, c.roi, ')

    if sortby == 'power':
        query = query + 'p.power DESC, c.verification_time DESC NULLS LAST, c.time DESC), '
    elif sortby == 'date':
        query = query + 'c.verification_time DESC NULLS LAST, c.time DESC, p.power DESC), '
    else:
        print("UNKNOWN SORTBY: " + sortby)
        return

    query = query + ('CF AS ( '
                     'SELECT * FROM CA WHERE classification_id = %s '
                     ')')

    params.append(classID)

    if len(tagIDs) == 0 or not (tagIDs[0] == 'ANY' or tagIDs[0] == 'SMART'):

        query = query + (''
                         ', '
                         'TA AS ( '
                         'SELECT DISTINCT ON (t.bin, t.roi, t.tag_id) t.*, p.power '
                         'FROM classify_tag t, auth_user_groups g, auth_group p '
                         'WHERE t.user_id = g.user_id '
                         'AND p.id = g.group_id '
                         'AND t.bin IN (')

        for bin in bins:
            query += '%s, '
            params.append(bin)

        query = query[:-2]

        query = query + ') ORDER BY t.bin, t.roi, t.tag_id, '

        if sortby == 'power':
            query = query + 'p.power DESC, t.verification_time DESC NULLS LAST, t.time DESC)'
        elif sortby == 'date':
            query = query + 't.verification_time DESC NULLS LAST, t.time DESC, p.power DESC)'

        if len(tagIDs) > 0:

            query = query + (', '
                             'TF AS ( '
                             'SELECT bin, roi, COUNT(*) AS cnt FROM TA '
                             'WHERE negation = false AND tag_id in (')

            for id in tagIDs:
                query += '%s, '
                params.append(id)

            query = query[:-2] + ') GROUP BY (bin, roi)'

            query = query + ('), PC AS ('
                             'SELECT bin, roi, COUNT(*) AS cnt FROM TA '
                             'WHERE negation = false GROUP BY (bin, roi))'
                             )

            query = query + ('SELECT DISTINCT ON (bin) CF.bin FROM TF, CF, PC '
                             'WHERE TF.roi = CF.roi AND TF.bin = CF.bin '
                             'AND CF.bin = PC.bin AND CF.roi = PC.roi '
                             'AND PC.cnt = TF.cnt AND PC.cnt = ' + str(len(tagIDs)) + ';'
                             )

        else:

            query = query + (' SELECT DISTINCT ON (bin) bin FROM CF '
                             'WHERE bin || \'_\' || roi NOT IN ('
                             'SELECT CF.bin || \'_\' || CF.roi AS pid FROM CF, TA '
                             'WHERE CF.bin = TA.bin AND CF.roi = TA.roi'
                             ');')
    else:
        query = query + ' SELECT DISTINCT ON (bin) bin FROM CF;'

    conn = sql.connect(database=config.db, user=config.username, password=config.password, host=config.server)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    rows = cur.fetchall()

    # print(cur.query)

    good_bins = []

    for row in rows:
        good_bins.append(row[0])

    # print("View: [" + str(classID) + ", " + str(tagIDs) + "]")
    # print(good_bins)

    print("iteration took " + str(time.time() - t1) + " seconds")
    good_bins.extend(filterBins(bins, views[1:], sortby))

    return utils.removeDuplicates(good_bins)


# we cache timeseries info here, so we don't make the same call to the database thousands of times
# format:
#    URL : UUID
timeseries_ids = {}


def getTimeseriesId(url):
    if url in timeseries_ids:
        return timeseries_ids[url]
    else:
        ts = Timeseries.objects.get(url=url).pk
        timeseries_ids[url] = str(ts)
        return ts


def loadAllTimeseries():
    global timeseries_ids
    timeseries_ids = {}
    try:
        for ts in Timeseries.objects.all():
            timeseries_ids[ts.url] = str(ts.pk)
    except:
        logger.error('Failed to load timeseries IDs, does the table exist?')


def getClassificationList():
    data = []
    for cl in ClassLabel.objects.all():
        c = {}
        c['id'] = cl.pk
        c['name'] = cl.name
        c['international_id'] = cl.international_id
        data.append(c)
    data = sorted(data, key=lambda c: c['name'].lower())
    data.insert(0, NO_ANNOTATION_CLASS)
    data.insert(0, NO_MATCH_CLASS)
    return data


def getTagList():
    data = []
    for tl in TagLabel.objects.all():
        c = {}
        c['id'] = tl.pk
        c['name'] = tl.name
        data.append(c)
    data = sorted(data, key=lambda c: c['name'].lower())
    return data;


# adds annotations based on the auto classifier results to the data being prepared for passing to the client

# Param 1: an array of strings, each representing a bin that's included in the data
# Param 2: an array with dictionary values; in each dictionary are "name", "id", and "international_id" keys representing values
#     for a given classification label
# Param 3: an array with dictionary values; in each dictionary are "name" and "id" keys representing values
#    for a given tag label
# Param 4: a dictionary, indexed by pid and produced by database.getAllDataForBins(), containing all annotations for the given bins
# Output: the same dictionary given in Param 4, modified to include annotations from the auto classifier

def addClassifierData(bins, classes, tags, data, timeseries):
    class_dict = {}
    tag_dict = {}
    # array to dict for faster access
    for c in classes:
        class_dict[c['name']] = c
    for t in tags:
        tag_dict[t['name']] = t

    for bin in bins:
        auto_results = utils.getAutoResultsForBin(bin, timeseries)
        if not auto_results:
            continue;
        for pid, classification in auto_results.items():
            name, tags = utils.convertClassifierName(classification)
            if name in class_dict:
                classification_id = class_dict[name]['id']
            else:
                logging.error(
                    "Auto classifier label '" + classification + "' had no matching class label. Expected '" + name + "'.")
                classification_id = NO_MATCH_CLASS['id']
            if not pid in data:
                continue

            c_dict = {
                'user_id': -1,
                'classification_id': classification_id,
                'level': 1,
                'timeseries_id': getTimeseriesId(timeseries),
                'user_power': -1,
                'username': 'auto',
            }

            for tag in tags:
                if tag in tag_dict:
                    t_dict = {
                        'user_id': -1,
                        'tag_id': tag_dict[tag]['id'],
                        'user_power': -1,
                        'level': 1,
                        'timeseries_id': getTimeseriesId(timeseries),
                        'username': 'auto',
                    }
                    data[pid]['tags'].append(t_dict)
                else:
                    logging.error(
                        "Auto classifier label '" + classification + "' had no matching tab label. Expected '" + tag + "'.")
                    c_dict['classification_id'] = NO_MATCH_CLASS['id']

            data[pid]['classifications'].append(c_dict)

    return data
