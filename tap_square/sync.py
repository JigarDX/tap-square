import singer
from singer import Transformer, metadata
from .client import SquareClient
from .streams import STREAMS


LOGGER = singer.get_logger()

def sync(config, state, catalog):
    client = SquareClient(config)

    with Transformer() as transformer:
        for stream in catalog.get_selected_streams(state):
            tap_stream_id = stream.tap_stream_id
            stream_obj = STREAMS[tap_stream_id]()
            replication_key = stream_obj.replication_key
            stream_schema = stream.schema.to_dict()
            stream_metadata = metadata.to_map(stream.metadata)

            LOGGER.info('Staring sync for stream: %s', tap_stream_id)

            state = singer.set_currently_syncing(state, tap_stream_id)
            singer.write_state(state)

            singer.write_schema(
                tap_stream_id,
                stream_schema,
                stream_obj.key_properties,
                stream.replication_key
            )

            start_time = singer.get_bookmark(state, tap_stream_id, replication_key, config['start_date'])
            bookmarked_cursor = singer.get_bookmark(state, tap_stream_id, 'cursor')

            if stream_obj.replication_method == 'INCREMENTAL':
                max_updated_at = start_time
                for page, cursor in stream_obj.sync(client, start_time, bookmarked_cursor):
                    
                    for record in page:
                        singer.write_record(
                            tap_stream_id,
                            transformer.transform(
                                record, stream_schema, stream_metadata,
                            ))
                        if record['updated_at'] > max_updated_at:
                            max_updated_at = record['updated_at']

                    state = singer.write_bookmark(state, tap_stream_id, 'cursor', cursor)
                    state = singer.write_bookmark(state, tap_stream_id, replication_key, max_updated_at)
                    singer.write_state(state)

            else:
                for page, cursor in stream_obj.sync(client, bookmarked_cursor):
                    for record in page:
                        singer.write_record(
                            tap_stream_id,
                            transformer.transform(
                                record, stream_schema, stream_metadata,
                            ))
                    state = singer.write_bookmark(state, tap_stream_id, 'cursor', cursor)
                    singer.write_state(state)
            state = singer.clear_bookmark(state, tap_stream_id, 'cursor')
            singer.write_state(state)

    state = singer.set_currently_syncing(state, None)
    singer.write_state(state)